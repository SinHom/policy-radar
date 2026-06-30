"""政策聚合卡片(每周推送,range=week/month/all 三种粒度)。

过滤规则(用户 2026-06-30 需求):
- 范围:region ∈ {河北, 秦皇岛, 秦皇岛市} OR region LIKE '%河北%' OR region LIKE '%秦皇岛%'
- 部门:department LIKE '%文旅%' OR department LIKE '%商务%' OR department LIKE '%旅游%' OR department LIKE '%招商%'
- 候选池:crawled_at >= (近 180 天)
- 推送池:已 success 推送过的不重推(从 push_logs 查,近 30 天窗口)
- AI 解读:200-300 字(最多 500),首句给"重点词/要点"
- 卡片 UI:
  - header 标题不带"早间简报",只用日期
  - 底部只显示北京时间(2026-06-30 15:32 北京)
  - 时间格式 2026年6月15日
  - 每条政策 标题 [title](url) 是可点击的(md 链接)
  - 不带"政策雷达管理"按钮
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, not_, select

from python.models import Policy, PolicySource, PushLog, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)

# ============== 北京时间工具 ==============
# 容器时区是 UTC,所有用户可见时间(卡片 / 推送时间 / 推送日的"周报"日期)
# 一律转 Asia/Shanghai 显示。
try:
    from zoneinfo import ZoneInfo  # py 3.9+
    BJ_TZ = ZoneInfo("Asia/Shanghai")
except ImportError:
    BJ_TZ = None  # fallback 退回到 +8h 偏移


def _now_bj() -> datetime:
    """当前北京时间(naive datetime,值是上海时区的 wall clock)。"""
    if BJ_TZ:
        return datetime.now(BJ_TZ).replace(tzinfo=None)
    return datetime.utcnow() + timedelta(hours=8)


def _to_bj(dt) -> datetime:
    """UTC datetime → 北京时间 naive(若 dt 无 tzinfo,视作 UTC)。"""
    if dt is None:
        return None  # type: ignore
    if dt.tzinfo is None:
        # naive → 视作 UTC
        if BJ_TZ:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            return dt + timedelta(hours=8)
    return dt.astimezone(BJ_TZ).replace(tzinfo=None)


# 卡片最大支持 50 个 element,每条政策占 4-5 个,实际 8-10 条政策
MAX_POLICIES_PER_CARD = 10

# 范围过滤
ALLOWED_REGIONS = ("河北", "秦皇岛", "秦皇岛市")
ALLOWED_DEPT_KEYWORDS = ("文旅", "商务", "旅游", "招商", "文广旅", "投促", "贸促")

# 推送去重窗口(近 30 天内已成功推送过的不重推)
DEDUP_WINDOW_DAYS = 30
# 候选池窗口
CANDIDATE_WINDOW_DAYS = 180


def _fmt_date(dt) -> str:
    """datetime → 2026年6月15日 风格,空/None 返空串。

    若 dt 是 naive,视作 UTC,转北京时区后输出(因为 DB 存的是 UTC 字符串)。
    """
    if not dt:
        return ""
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", ""))
        if dt is None:
            return ""
        # 转到北京时间
        dt_bj = _to_bj(dt)
        return f"{dt_bj.year}年{dt_bj.month}月{dt_bj.day}日"
    except Exception:
        return str(dt)[:10] if dt else ""


def _fmt_time(dt) -> str:
    """datetime → HH:MM(北京时间)"""
    if not dt:
        return ""
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", ""))
        if dt is None:
            return ""
        dt_bj = _to_bj(dt)
        return dt_bj.strftime("%H:%M")
    except Exception:
        return ""


def _region_match(region: str | None) -> bool:
    """region 在 ALLOWED_REGIONS 或含河北/秦皇岛。"""
    if not region:
        return False
    if region in ALLOWED_REGIONS:
        return True
    if "河北" in region or "秦皇岛" in region:
        return True
    return False


def _dept_match(department: str | None, source_name: str | None) -> bool:
    """department 或 source_name 命中关键词。"""
    text = (department or "") + " " + (source_name or "")
    for kw in ALLOWED_DEPT_KEYWORDS:
        if kw in text:
            return True
    return False


def _build_weekly_card(
    rows: list[dict],
    week_label: str,
    push_time: str,
) -> dict:
    """周报聚合卡片(最多 MAX_POLICIES_PER_CARD 条/卡)。"""
    header_title = f"📡 政策雷达 · {week_label}"

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
                            "content": f"**{week_label}** · 本周暂无新增匹配政策(范围:河北/秦皇岛 · 文旅/商务)。",
                        },
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"<font color='grey'>推送时间: {push_time} (北京时间)</font>",
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
            "content": f"**{week_label}** · 本周新增 **{len(rows)}** 篇匹配政策",
        },
    })
    elements.append({"tag": "hr"})

    for i, r in enumerate(rows, 1):
        # 标题可点击 md 链接
        content_lines: list[str] = [f"**{i}. [{r['title']}]({r['url']})**"]
        if r["summary"]:
            content_lines.append(f"> {r['summary']}")

        # 元信息
        meta_parts: list[str] = []
        if r["pub_date"]:
            meta_parts.append(f"📅 {r['pub_date']}")
        if r["source_name"]:
            meta_parts.append(f"📌 {r['source_name']}")
        if r["region"]:
            meta_parts.append(f"📍 {r['region']}")
        if meta_parts:
            content_lines.append("  ·  ".join(meta_parts))

        # 操作链接
        action_parts: list[str] = []
        if r["url"]:
            action_parts.append(f"[👉 阅读原文]({r['url']})")
        if r["pol_id"]:
            action_parts.append(f"[📄 下载 PDF](/api/policies/{r['pol_id']}/pdf)")
        if action_parts:
            content_lines.append("  ·  ".join(action_parts))

        # AI 解读(200-300 字)
        if r["advisory"]:
            content_lines.append("")
            content_lines.append(f"💡 **AI 解读**")
            content_lines.append(r["advisory"])

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(content_lines)},
        })
        elements.append({"tag": "hr"})

    # 底部:北京时间
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"<font color='grey'>推送时间: {push_time} (北京时间)</font>",
        },
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
    """Policy 对象扁平化(dict),所有属性访问在 session 内完成。"""
    if not policies:
        return []
    src_ids = {p.source_id for p in policies if p.source_id}
    sources_by_id: dict[int, tuple[str, str, str]] = {}
    if src_ids:
        async with get_session() as session:
            stmt = select(PolicySource).where(PolicySource.id.in_(src_ids))
            srcs = (await session.execute(stmt)).scalars().all()
            sources_by_id = {s.id: (s.name or "", s.region or "", s.department or "") for s in srcs}
            return [
                {
                    "pol_id": p.id,
                    "title": p.title or "无标题",
                    "url": p.url or "",
                    "summary": (p.summary_text or "").strip(),
                    "advisory": (p.advisory or "").strip(),
                    "pub_date": _fmt_date(p.published_at or p.crawled_at),
                    "source_name": sources_by_id.get(p.source_id, ("", "", ""))[0],
                    "region": sources_by_id.get(p.source_id, ("", "", ""))[1],
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
            "pub_date": _fmt_date(p.published_at or p.crawled_at),
            "source_name": "",
            "region": "",
        }
        for p in policies
    ]


async def _select_weekly_policies(
    slot: str = "weekly",
    window_days: int = 30,
) -> list[Policy]:
    """选近 window_days 天爬取 + 范围匹配 + 已成功推送过的不重推 的政策。"""
    # cutoff 用北京时间计算(用户认知一致),然后转 UTC ISO 跟 DB 比
    now_bj = _now_bj()
    now_utc = datetime.utcnow()
    # 用 UTC 比较(因为 DB crawled_at 是 UTC 字符串)
    candidate_cutoff_utc = now_utc - timedelta(days=CANDIDATE_WINDOW_DAYS)
    dedup_cutoff_utc = now_utc - timedelta(days=DEDUP_WINDOW_DAYS)

    async with get_session() as session:
        # 1) 已推过的 policy_id 集合
        stmt_pushed = (
            select(PushLog.policy_id)
            .where(PushLog.status == "success")
            .where(PushLog.created_at >= dedup_cutoff_utc)
            .where(PushLog.policy_id.isnot(None))
            .distinct()
        )
        pushed_ids = set((await session.execute(stmt_pushed)).scalars().all())

        # 2) 候选:近 180 天 + 已摘要 + 不在已推集合
        cutoff_iso = candidate_cutoff_utc.isoformat()
        stmt = (
            select(Policy)
            .where(Policy.crawled_at >= cutoff_iso)
            .where(Policy.summary_text.isnot(None))
            .order_by(desc(Policy.id))
            .limit(200)
        )
        if pushed_ids:
            stmt = stmt.where(Policy.id.notin_(pushed_ids))
        policies = list((await session.execute(stmt)).scalars().all())

    # 3) 客户端过滤 region + department
    src_ids_needed = {p.source_id for p in policies if p.source_id}
    src_meta: dict[int, tuple[str, str, str]] = {}
    if src_ids_needed:
        async with get_session() as session:
            stmt_src = select(PolicySource).where(PolicySource.id.in_(src_ids_needed))
            srcs = (await session.execute(stmt_src)).scalars().all()
            src_meta = {s.id: (s.name or "", s.region or "", s.department or "") for s in srcs}

    # 第一道:name 匹配
    filtered: list[Policy] = []
    for p in policies:
        src_name, src_region, _ = src_meta.get(p.source_id, ("", "", ""))
        region_match = _region_match(src_region) or "河北" in (src_name or "") or "秦皇岛" in (src_name or "")
        dept_match = _dept_match(src_name, src_name)
        if region_match and dept_match:
            filtered.append(p)

    # Fallback:用 source.department 字段(例 "河北省文化和旅游厅" 含 "文旅")
    if not filtered:
        for p in policies:
            if p in filtered:
                continue
            src_name, src_region, src_dept = src_meta.get(p.source_id, ("", "", ""))
            region_match = _region_match(src_region) or "河北" in (src_name or "") or "秦皇岛" in (src_name or "")
            dept_match = _dept_match(src_dept, src_name)
            if region_match and dept_match:
                filtered.append(p)

    return filtered[:50]


async def build_weekly_report(slot: str = "weekly") -> list[dict]:
    """构建周报卡片(范围近 30 天,按北京时区算"周报日")。"""
    now_bj = _now_bj()
    week_label = f"{now_bj.month}月{now_bj.day}日周报"
    push_time = now_bj.strftime("%Y-%m-%d %H:%M")

    policies = await _select_weekly_policies(slot=slot, window_days=DEDUP_WINDOW_DAYS)
    if not policies:
        return [_build_weekly_card([], week_label, push_time)]

    rows = await _flatten_policies(policies)

    cards: list[dict] = []
    for i in range(0, len(rows), MAX_POLICIES_PER_CARD):
        chunk = rows[i : i + MAX_POLICIES_PER_CARD]
        cards.append(_build_weekly_card(chunk, week_label, push_time))
    return cards


async def send_weekly_report(
    subscription_id: int,
    slot: str = "weekly",
) -> dict:
    """对单条订阅生成周报并推送(feishu/webhook)。"""
    from sqlalchemy.orm import joinedload
    async with get_session() as session:
        stmt = (
            select(Subscription)
            .where(Subscription.id == subscription_id)
            .options(joinedload(Subscription.company))
        )
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            return {"ok": False, "error": "subscription not found"}
        if not sub.enabled:
            return {"ok": False, "error": "subscription disabled"}
        channel = sub.push_channel or "feishu"
        if channel not in ("feishu", "webhook"):
            return {"ok": False, "error": f"weekly_report 只支持 feishu/webhook (got {channel})"}
        config = dict(sub.push_config or {})
        if not config.get("webhook_url"):
            return {"ok": False, "error": "push_config.webhook_url 未配置"}
        company_name = sub.company.name if sub.company else None

    cards = await build_weekly_report(slot)
    if not cards:
        return {"ok": False, "error": "no cards generated"}

    from python.app.push.facade import push_daily_cards
    return await push_daily_cards(cards, channel, config, company_name=company_name)