"""日报聚合卡片:一次推 N 条政策,做成"今日新增 N 篇"卡片(仿 wechat-crawler)。

卡片结构:
  header: 📡 政策雷达 · 早间/午间/晚间简报
  [div] **2026-06-30** · 共 5 篇新政策
  [hr]
  [div] **1. [政策标题](url)**
       [摘要]
       ⏰ 09:30 · [👉 阅读原文](url) · [📄 下载 PDF](/api/policies/{id}/pdf)
       💡 _AI 解读:200字内_
  [hr]
  ...
  [note] 政策雷达 · 早间简报 · 共 N 篇
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select

from python.models import Policy, PolicySource, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)

# 卡片最大支持 50 个 element,每条政策占 4 个(div+hr+div+hr),
# 留 1 个 header + 1 个 footer + 1 个分隔 = 3 个,实际可放 ~12 条政策
# 超过 12 条时分多条卡片
MAX_POLICIES_PER_CARD = 12
DAILY_REPORT_FALLBACK_ADMIN = "http://43.155.161.54:8000/admin"


def _fmt_dt(dt) -> str:
    """datetime → HH:MM,空/None 返空串。"""
    if not dt:
        return ""
    try:
        s = str(dt)
        if " " in s:
            return s.split(" ")[1][:5]
        if "T" in s:
            return s.split("T")[1][:5]
        return s[-5:]
    except Exception:
        return ""


def _build_daily_card(
    rows: list[dict],
    slot: str,
    date_str: str,
) -> dict:
    """构造飞书交互式卡片。

    rows: list[{pol_id, title, url, summary, advisory, dt_str, source_name}, ...]
    (扁平化,避免 session 外访问 ORM 对象的 lazy attribute)
    """
    slot_emoji = {"早间": "🌅", "午间": "☀️", "晚间": "🌙"}.get(slot, "📡")
    header_title = f"{slot_emoji} 政策雷达 · {slot}简报"

    if not rows:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": header_title},
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{date_str}** · 暂无新政策(可能被全部去重或尚未抓取)",
                        },
                    },
                ],
            },
        }

    elements: list[dict] = []
    # 头部摘要
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**{date_str}** · 共 **{len(rows)}** 篇新政策",
        },
    })
    elements.append({"tag": "hr"})

    for i, r in enumerate(rows, 1):
        content_lines: list[str] = [f"**{i}. [{r['title']}]({r['url']})**"]
        if r["summary"]:
            content_lines.append(r["summary"])
        meta_parts: list[str] = []
        if r["dt_str"]:
            meta_parts.append(f"⏰ {r['dt_str']}")
        if r["source_name"]:
            meta_parts.append(f"📌 {r['source_name']}")
        meta_parts.append(f"[👉 阅读原文]({r['url']})")
        if r["pol_id"]:
            meta_parts.append(f"[📄 下载 PDF](/api/policies/{r['pol_id']}/pdf)")
        content_lines.append("  ·  ".join(meta_parts))
        if r["advisory"]:
            content_lines.append(f"💡 _{r['advisory']}_")

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(content_lines)},
        })
        elements.append({"tag": "hr"})

    # 底部
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"<font color='grey'>📡 政策雷达 · 早间/午间/晚间简报 · {datetime.now().strftime('%H:%M:%S')}</font>",
        },
    })
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🌐 政策雷达管理"},
                "type": "default",
                "url": DAILY_REPORT_FALLBACK_ADMIN,
            },
        ],
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": "blue",
            },
            "elements": elements,
        },
    }


async def _flatten_policies(policies: list) -> list[dict]:
    """把 Policy 对象扁平化成 dict,在 session 内完成所有属性访问。"""
    if not policies:
        return []
    src_ids = {p.source_id for p in policies if p.source_id}
    sources_by_id: dict[int, str] = {}
    if src_ids:
        async with get_session() as session:
            stmt = select(PolicySource).where(PolicySource.id.in_(src_ids))
            srcs = (await session.execute(stmt)).scalars().all()
            sources_by_id = {s.id: s.name for s in srcs}
            # 同样在 session 内取所有字段(避免 lazy load)
            return [
                {
                    "pol_id": p.id,
                    "title": p.title or "无标题",
                    "url": p.url or "",
                    "summary": (p.summary_text or "").strip(),
                    "advisory": (p.advisory or "").strip(),
                    "dt_str": _fmt_dt(p.published_at or p.crawled_at),
                    "source_name": sources_by_id.get(p.source_id, ""),
                }
                for p in policies
            ]
    return [
        {
            "pol_id": p.id,
            "title": p.title or "无标题",
            "url": p.url or "",
            "summary": (p.summary_text or "").strip(),
            "advisory": (p.advisory or "").strip(),
            "dt_str": _fmt_dt(p.published_at or p.crawled_at),
            "source_name": "",
        }
        for p in policies
    ]


async def _select_policies_for_slot(slot: str, since_hours: int) -> list[Policy]:
    """取最近 since_hours 小时抓取且已摘要的政策(返回 ORM 对象,后续在 session 内 flatten)。"""
    delta = {"早间": 12, "午间": 5, "晚间": 8}.get(slot, 6)
    cutoff = datetime.utcnow() - timedelta(hours=delta)
    async with get_session() as session:
        stmt = (
            select(Policy)
            .where(Policy.crawled_at >= cutoff)
            .where(Policy.summary_text.isnot(None))  # 已摘要
            .order_by(desc(Policy.id))
            .limit(50)
        )
        return list((await session.execute(stmt)).scalars().all())


async def build_daily_report(slot: str = "早间") -> list[dict]:
    """构建日报聚合卡片列表(可能 1 张或 N 张,N = ceil(条数 / MAX_POLICIES_PER_CARD))。

    所有数据访问都在 session 内完成,返回纯 dict 列表(session 外可安全使用)。
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    policies = await _select_policies_for_slot(slot, since_hours={"早间": 12, "午间": 5, "晚间": 8}.get(slot, 6))
    if not policies:
        return [_build_daily_card([], slot, date_str)]

    rows = await _flatten_policies(policies)

    cards: list[dict] = []
    for i in range(0, len(rows), MAX_POLICIES_PER_CARD):
        chunk = rows[i : i + MAX_POLICIES_PER_CARD]
        cards.append(_build_daily_card(chunk, slot, date_str))
    return cards


async def send_daily_report(
    subscription_id: int,
    slot: str = "早间",
) -> dict:
    """对单条订阅生成日报并推送(feishu channel)。"""
    async with get_session() as session:
        sub = await session.get(Subscription, subscription_id)
        if not sub:
            return {"ok": False, "error": "subscription not found"}
        if not sub.enabled:
            return {"ok": False, "error": "subscription disabled"}
        channel = sub.push_channel or "feishu"
        if channel != "feishu":
            return {"ok": False, "error": f"daily_report 目前只支持 feishu channel (got {channel})"}
        config = sub.push_config or {}
        if not config.get("webhook_url"):
            return {"ok": False, "error": "push_config.webhook_url 未配置"}
        # 注意:SQLAlchemy 2.0 async 中,必须 session 内访问 relationship(sub.company)
        comp = sub.company
        company_name = comp.name if comp else None

    cards = await build_daily_report(slot)
    if not cards:
        return {"ok": False, "error": "no cards generated"}

    from python.app.push.facade import push_daily_cards
    return await push_daily_cards(cards, channel, config, company_name=company_name)
