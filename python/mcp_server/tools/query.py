"""查询类 Tools：search_policies / get_matches / get_policy_detail。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, or_, select

from python.models import Company, Match, Policy, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)


def _policy_to_dict(p: Policy, include_url: bool = True) -> dict:
    data = {
        "id": p.id,
        "title": p.title,
        "type": p.summary_type,
        "summary": p.summary_text,
        "amount": (p.summary_data or {}).get("amount") if p.summary_data else None,
        "deadline": (p.summary_data or {}).get("deadline") if p.summary_data else None,
        "keywords": (p.summary_data or {}).get("keywords", []) if p.summary_data else [],
        "conditions": (p.summary_data or {}).get("conditions", []) if p.summary_data else [],
        "target_enterprise": (p.summary_data or {}).get("target_enterprise") if p.summary_data else None,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "summarized_at": p.summarized_at.isoformat() if p.summarized_at else None,
    }
    if include_url:
        data["url"] = p.url
    return data


async def handle_search_policies(arguments: dict) -> list[dict]:
    """search_policies 实现。"""
    query = arguments.get("query")
    types = arguments.get("types") or []
    region = arguments.get("region")
    days_back = int(arguments.get("days_back") or 30)
    limit = int(arguments.get("limit") or 20)
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    async with get_session() as session:
        stmt = select(Policy).where(Policy.summary_text.isnot(None))
        if days_back > 0:
            stmt = stmt.where(Policy.crawled_at >= cutoff)
        if types:
            stmt = stmt.where(Policy.summary_type.in_(types))
        if region:
            stmt = stmt.where(or_(
                Policy.title.contains(region),
                Policy.raw_content.contains(region),
            ))
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(
                Policy.title.contains(query),
                Policy.summary_text.contains(query),
            ))
        stmt = stmt.order_by(desc(Policy.id)).limit(limit)
        rows = list((await session.execute(stmt)).scalars().all())

    return [{
        "type": "text",
        "text": json.dumps({
            "status": "ok",
            "count": len(rows),
            "policies": [_policy_to_dict(p) for p in rows],
        }, ensure_ascii=False),
    }]


async def handle_get_matches(arguments: dict) -> list[dict]:
    """get_matches 实现。"""
    company_id = arguments.get("company_id")
    if not company_id:
        return [{
            "type": "text",
            "text": json.dumps({"status": "error", "error": "company_id is required"}, ensure_ascii=False),
        }]
    limit = int(arguments.get("limit") or 10)
    unpushed_only = bool(arguments.get("unpushed_only", False))

    async with get_session() as session:
        # 取 subscription
        stmt = select(Subscription).where(Subscription.company_id == company_id)
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if sub is None:
            return [{
                "type": "text",
                "text": json.dumps(
                    {"status": "error", "error": f"company {company_id} has no subscription"},
                    ensure_ascii=False,
                ),
            }]

        # 查 matches
        stmt2 = (
            select(Match, Policy)
            .join(Policy, Match.policy_id == Policy.id)
            .where(Match.subscription_id == sub.id)
        )
        if unpushed_only:
            stmt2 = stmt2.where(Match.pushed.is_(False))
        stmt2 = stmt2.order_by(desc(Match.score), desc(Match.id)).limit(limit)
        rows = list((await session.execute(stmt2)).all())

    return [{
        "type": "text",
        "text": json.dumps({
            "status": "ok",
            "company_id": company_id,
            "subscription_id": sub.id,
            "count": len(rows),
            "matches": [
                {
                    "match_id": m.id,
                    "score": m.score,
                    "reasons": m.reasons or [],
                    "pushed": m.pushed,
                    "pushed_at": m.pushed_at.isoformat() if m.pushed_at else None,
                    "policy": _policy_to_dict(p),
                }
                for m, p in rows
            ],
        }, ensure_ascii=False),
    }]


async def handle_get_policy_detail(arguments: dict) -> list[dict]:
    """get_policy_detail 实现。"""
    policy_id = arguments.get("policy_id")
    if not policy_id:
        return [{
            "type": "text",
            "text": json.dumps({"status": "error", "error": "policy_id is required"}, ensure_ascii=False),
        }]

    async with get_session() as session:
        stmt = select(Policy).where(Policy.id == policy_id)
        pol = (await session.execute(stmt)).scalar_one_or_none()
        if pol is None:
            return [{
                "type": "text",
                "text": json.dumps(
                    {"status": "error", "error": f"policy {policy_id} not found"},
                    ensure_ascii=False,
                ),
            }]

    data = _policy_to_dict(pol)
    data["raw_content"] = pol.raw_content  # 详情页含全文
    return [{
        "type": "text",
        "text": json.dumps({"status": "ok", "policy": data}, ensure_ascii=False),
    }]
