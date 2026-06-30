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

from python.app.push.dispatcher import PushContent, PushResult
from python.models import Company, Policy, PolicySource, Subscription
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
    policies: list[Policy],
    sources_by_id: dict[int, PolicySource],
    slot: str,
    date_str: str,
) -> dict:
    """构造日报聚合卡片(最多 MAX_POLICIES_PER_CARD 条)。"""
    slot_emoji = {"早间": "🌅", "午间": "☀️", "晚间": "🌙"}.get(slot, "📡")
    header_title = f"{slot_emoji} 政策雷达 · {slot}简报"
    if len(policies) == 0:
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
            "content": f"**{date_str}** · 共 **{len(policies)}** 篇新政策",
        },
    })
    elements.append({"tag": "hr"})

    for i, pol in enumerate(policies, 1):
        title = pol.title or "无标题"
        url = pol.url
        summary = (pol.summary_text or "").strip()
        advisory = (pol.advisory or "").strip()
        dt_str = _fmt_dt(pol.published_at or pol.crawled_at)
        src = sources_by_id.get(pol.source_id)
        src_name = src.name if src else ""

        content_lines: list[str] = [f"**{i}. [{title}]({url})**"]
        if summary:
            content_lines.append(summary)
        # meta 行
        meta_parts: list[str] = []
        if dt_str:
            meta_parts.append(f"⏰ {dt_str}")
        if src_name:
            meta_parts.append(f"📌 {src_name}")
        meta_parts.append(f"[👉 阅读原文]({url})")
        if pol.id:
            meta_parts.append(f"[📄 下载 PDF](/api/policies/{pol.id}/pdf)")
        content_lines.append("  ·  ".join(meta_parts))
        if advisory:
            # 业务解读
            content_lines.append(f"💡 _{advisory}_")

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
    # 按钮:跳管理后台
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


async def _select_policies_for_slot(slot: str, since_hours: int) -> list[Policy]:
    """取最近 since_hours 小时抓取且未推送过的政策。

    slot=早/午/晚 决定 since_hours:
      早间:12  (昨晚 22:xx - 早 9:00)
      午间:5   (早 9:00 - 午 12:00)
      晚间:8   (午 12:00 - 晚 20:00)
    """
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

    包含每条政策的 PDF 链接,需要后端 /api/policies/{id}/pdf 在线生成。
    PDF 应该在 daily report 之前预热(可由 scheduler 单独跑)。
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    policies = await _select_policies_for_slot(slot, since_hours={"早间": 12, "午间": 5, "晚间": 8}.get(slot, 6))
    if not policies:
        return [_build_daily_card([], {}, slot, date_str)]

    # 拉 sources 一次
    src_ids = {p.source_id for p in policies}
    async with get_session() as session:
        stmt = select(PolicySource).where(PolicySource.id.in_(src_ids))
        srcs = (await session.execute(stmt)).scalars().all()
        sources_by_id = {s.id: s for s in srcs}

    cards: list[dict] = []
    for i in range(0, len(policies), MAX_POLICIES_PER_CARD):
        chunk = policies[i : i + MAX_POLICIES_PER_CARD]
        cards.append(_build_daily_card(chunk, sources_by_id, slot, date_str))
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
        # 准备 push_config
        config = sub.push_config or {}
        if not config.get("webhook_url"):
            return {"ok": False, "error": "push_config.webhook_url 未配置"}
        # 注意:SQLAlchemy 2.0 async 中,必须 session 内访问 relationship(sub.company)
        # 否则触发 MissingGreenlet(IO outside async context)
        comp = sub.company
        company_name = comp.name if comp else None

    cards = await build_daily_report(slot)
    if not cards:
        return {"ok": False, "error": "no cards generated"}

    # 用第一张卡片做"代表"创建 PushContent,实际上 daily_report 走特殊通道
    from python.app.push.facade import push_daily_cards  # lazy import 避免循环
    return await push_daily_cards(cards, channel, config, company_name=company_name)
