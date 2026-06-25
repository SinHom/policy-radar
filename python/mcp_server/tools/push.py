"""立即推送 Tool：push_now(company_id, match_ids?)。

设计：
- 不等定时任务，立即把 matches 推到该公司的 webhook
- match_ids 留空 → 推所有未推送
- match_ids 指定 → 只推指定（不管 pushed 状态）
- 推成功后标记 matches.pushed=True + pushed_at
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from python.models import Match, Policy, Subscription
from python.models.base import get_session
from python.mcp_server.webhook import push_to_webhook

logger = logging.getLogger(__name__)


async def handle_push_now(arguments: dict) -> list[dict]:
    """push_now 实现。"""
    company_id = arguments.get("company_id")
    if not company_id:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "company_id is required"},
                ensure_ascii=False,
            ),
        }]
    match_ids = arguments.get("match_ids")  # 可选

    async with get_session() as session:
        # 查 subscription（带 company）
        stmt = select(Subscription).where(
            Subscription.company_id == company_id
        ).options(selectinload(Subscription.company))
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if sub is None:
            return [{
                "type": "text",
                "text": json.dumps(
                    {"status": "error", "error": f"company {company_id} has no subscription"},
                    ensure_ascii=False,
                ),
            }]
        if not sub.webhook_url:
            return [{
                "type": "text",
                "text": json.dumps({
                    "status": "skipped",
                    "reason": "no webhook_url configured for this subscription; use get_matches for pull mode",
                }, ensure_ascii=False),
            }]

        # 查 matches
        stmt2 = (
            select(Match, Policy)
            .join(Policy, Match.policy_id == Policy.id)
            .where(Match.subscription_id == sub.id)
        )
        if match_ids:
            stmt2 = stmt2.where(Match.id.in_(match_ids))
        else:
            stmt2 = stmt2.where(Match.pushed.is_(False))
        stmt2 = stmt2.order_by(Match.score.desc()).limit(50)
        rows = list((await session.execute(stmt2)).all())
        if not rows:
            return [{
                "type": "text",
                "text": json.dumps({
                    "status": "ok",
                    "pushed": 0,
                    "message": "no matches to push (all pushed already, or none exist)",
                }, ensure_ascii=False),
            }]

        # 推
        result = await push_to_webhook(sub, rows)
        if result.get("ok"):
            pushed_ids = []
            for m, _ in rows:
                m.pushed = True
                m.pushed_at = datetime.utcnow()
                pushed_ids.append(m.id)
            sub.last_push_at = datetime.utcnow()
            return [{
                "type": "text",
                "text": json.dumps({
                    "status": "ok",
                    "pushed": len(pushed_ids),
                    "match_ids": pushed_ids,
                    "platform": result.get("platform"),
                    "message": f"已推送 {len(pushed_ids)} 条匹配到 webhook",
                }, ensure_ascii=False),
            }]
        else:
            return [{
                "type": "text",
                "text": json.dumps({
                    "status": "error",
                    "pushed": 0,
                    "error": result.get("error"),
                    "platform": result.get("platform"),
                }, ensure_ascii=False),
            }]
