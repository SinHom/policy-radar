"""注册引导类 Tools：start_setup / complete_setup / confirm_setup。

设计：MCP Server 无状态，AI 工具负责追问用户填字段。
- start_setup:  传入已知字段，返回缺失字段 + 每个字段的预设选项
- complete_setup: 补齐信息后调用，返回 ready_to_confirm 状态 + 摘要
- confirm_setup: 用户确认后落库，返回 company_id / subscription_id
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select

from python.models import Company, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)

# 字段定义：每个字段的选项 + 标题 + 必填 + 简介
FIELD_DEFINITIONS = {
    "industry": {
        "title": "所属行业",
        "options": ["科技/互联网", "制造业", "生物医药", "新能源", "金融", "其他"],
        "required": True,
    },
    "region": {
        "title": "企业注册地",
        "options": ["深圳", "广州", "北京", "上海", "杭州", "其他"],
        "required": True,
    },
    "policy_types": {
        "title": "关注的政策类型（可多选）",
        "options": ["补贴", "贷款", "税收优惠", "人才引进", "产业扶持", "知识产权", "科技项目"],
        "required": True,
        "multi": True,
    },
    "regions": {
        "title": "关注哪些地区的政策？（可多选）",
        "options": ["深圳", "广州", "北京", "上海", "浙江", "江苏", "广东（全省）", "全国"],
        "required": True,
        "multi": True,
    },
    "keywords": {
        "title": "关键词增强（可空，举例：高新技术、专精特新、研发）",
        "options": None,  # 自由输入
        "required": False,
    },
    "push_schedule": {
        "title": "推送频率",
        "options": ["realtime", "daily", "weekly", "manual"],
        "option_labels": {
            "realtime": "新政策立即推",
            "daily": "每日早间汇总（08:30）",
            "weekly": "每周五汇总",
            "manual": "不主动推，我自己查询",
        },
        "required": True,
    },
    "webhook_url": {
        "title": "推送 Webhook URL（可选，留空则只支持主动查询）",
        "options": None,
        "required": False,
    },
    "platform_hint": {
        "title": "平台提示（可选：feishu/wecom/generic）",
        "options": ["feishu", "wecom", "generic"],
        "required": False,
    },
}


def _check_missing(data: dict) -> list[dict]:
    """检查 data 里缺哪些 required 字段，返回缺失字段的追问列表。"""
    missing = []
    for field, defn in FIELD_DEFINITIONS.items():
        if not defn["required"]:
            continue
        val = data.get(field)
        if val is None or (isinstance(val, (list, str)) and not val):
            missing.append({
                "field": field,
                "question": defn["title"],
                "options": defn["options"],
                "multi": defn.get("multi", False),
            })
    return missing


def _format_summary(data: dict) -> dict:
    """格式化展示摘要（给 confirm_setup 显示用）。"""
    sched = data.get("push_schedule", "manual")
    sched_label = FIELD_DEFINITIONS["push_schedule"]["option_labels"].get(sched, sched)
    return {
        "company_name": data.get("company_name"),
        "industry": data.get("industry"),
        "region": data.get("region"),
        "policy_types": data.get("policy_types") or [],
        "regions": data.get("regions") or [],
        "keywords": data.get("keywords") or [],
        "push_schedule": sched,
        "push_schedule_label": sched_label,
        "webhook_url": data.get("webhook_url"),
        "platform_hint": data.get("platform_hint"),
    }


async def handle_start_setup(arguments: dict) -> list[dict]:
    """start_setup 实现。

    1. 校验 company_name 必填
    2. 检查缺失字段
    3. 返回 filled / missing / status
    """
    company_name = arguments.get("company_name")
    if not company_name:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "company_name is required"},
                ensure_ascii=False,
            ),
        }]

    # 查重：同名 company
    async with get_session() as session:
        stmt = select(Company).where(Company.name == company_name)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            # 已存在：返回现有信息让用户确认/更新
            stmt2 = select(Subscription).where(Subscription.company_id == existing.id)
            sub = (await session.execute(stmt2)).scalar_one_or_none()
            filled = {
                "company_name": existing.name,
                "industry": existing.industry,
                "region": existing.region,
            }
            if sub:
                filled.update({
                    "policy_types": sub.types,
                    "regions": sub.regions,
                    "keywords": sub.keywords,
                    "push_schedule": sub.push_schedule,
                    "webhook_url": sub.webhook_url,
                    "platform_hint": sub.platform_hint,
                })
            missing = _check_missing(filled)
            return [{
                "type": "text",
                "text": json.dumps({
                    "status": "existing_company" if not missing else "need_more_info",
                    "company_id": existing.id,
                    "subscription_id": sub.id if sub else None,
                    "filled": {k: v for k, v in filled.items() if v},
                    "missing": missing,
                }, ensure_ascii=False),
            }]

    # 新公司
    filled = {k: v for k, v in arguments.items() if v}
    missing = _check_missing(filled)
    if missing:
        return [{
            "type": "text",
            "text": json.dumps({
                "status": "need_more_info",
                "filled": filled,
                "missing": missing,
            }, ensure_ascii=False),
        }]

    # 信息齐全
    summary = _format_summary(filled)
    return [{
        "type": "text",
        "text": json.dumps({
            "status": "ready_to_confirm",
            "summary": summary,
            "confirm_prompt": _build_confirm_prompt(summary),
        }, ensure_ascii=False),
    }]


def _build_confirm_prompt(s: dict) -> str:
    types_str = "、".join(s["policy_types"]) if s["policy_types"] else "（未指定）"
    regions_str = "、".join(s["regions"]) if s["regions"] else "（未指定）"
    kw_str = "、".join(s["keywords"]) if s["keywords"] else "（无）"
    push_label = s.get("push_schedule_label", s["push_schedule"])
    return (
        f"请确认以下信息：\n\n"
        f"• 企业名称：{s['company_name']}\n"
        f"• 行业：{s['industry']}\n"
        f"• 注册地：{s['region']}\n"
        f"• 关注的政策类型：{types_str}\n"
        f"• 关注的地区：{regions_str}\n"
        f"• 关键词增强：{kw_str}\n"
        f"• 推送频率：{push_label}\n"
        f"• Webhook：{s.get('webhook_url') or '（未设）'}\n\n"
        f"确认后请调用 confirm_setup 完成注册。"
    )


async def handle_complete_setup(arguments: dict) -> list[dict]:
    """complete_setup：补齐信息后返回 ready_to_confirm。"""
    company_name = arguments.get("company_name")
    if not company_name:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "company_name is required"},
                ensure_ascii=False,
            ),
        }]
    missing = _check_missing(arguments)
    if missing:
        return [{
            "type": "text",
            "text": json.dumps({
                "status": "need_more_info",
                "filled": {k: v for k, v in arguments.items() if v},
                "missing": missing,
            }, ensure_ascii=False),
        }]
    summary = _format_summary(arguments)
    return [{
        "type": "text",
        "text": json.dumps({
            "status": "ready_to_confirm",
            "summary": summary,
            "confirm_prompt": _build_confirm_prompt(summary),
        }, ensure_ascii=False),
    }]


async def handle_confirm_setup(arguments: dict) -> list[dict]:
    """confirm_setup：落库。参数是 complete_setup 返回的 summary 对象。"""
    data = arguments.get("setup_data") or arguments
    company_name = data.get("company_name")
    if not company_name:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "company_name is required in setup_data"},
                ensure_ascii=False,
            ),
        }]

    # 落库
    async with get_session() as session:
        # upsert company
        stmt = select(Company).where(Company.name == company_name)
        comp = (await session.execute(stmt)).scalar_one_or_none()
        if comp is None:
            comp = Company(
                name=company_name,
                industry=data.get("industry"),
                region=data.get("region"),
                tags=data.get("tags"),
            )
            session.add(comp)
            await session.flush()  # 拿 id
        else:
            comp.industry = data.get("industry") or comp.industry
            comp.region = data.get("region") or comp.region

        # upsert subscription (1 company : 1 sub)
        stmt2 = select(Subscription).where(Subscription.company_id == comp.id)
        sub = (await session.execute(stmt2)).scalar_one_or_none()
        if sub is None:
            sub = Subscription(
                company_id=comp.id,
                types=data.get("policy_types") or [],
                regions=data.get("regions") or [],
                keywords=data.get("keywords") or [],
                push_schedule=data.get("push_schedule", "daily"),
                push_time=data.get("push_time", "08:30"),
                webhook_url=data.get("webhook_url"),
                platform_hint=data.get("platform_hint"),
                enabled=True,
            )
            session.add(sub)
            await session.flush()
        else:
            sub.types = data.get("policy_types") or sub.types
            sub.regions = data.get("regions") or sub.regions
            sub.keywords = data.get("keywords") or sub.keywords
            sub.push_schedule = data.get("push_schedule", sub.push_schedule)
            sub.webhook_url = data.get("webhook_url", sub.webhook_url)
            sub.platform_hint = data.get("platform_hint", sub.platform_hint)

        return [{
            "type": "text",
            "text": json.dumps({
                "status": "ok",
                "company_id": comp.id,
                "subscription_id": sub.id,
                "message": f"注册成功！企业 {comp.name} 已开始监控。",
            }, ensure_ascii=False),
        }]
