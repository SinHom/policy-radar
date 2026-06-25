"""订阅管理类 Tools：update_subscription / pause_subscription / resume_subscription / delete_subscription。

设计：
- 传 company_id 或 subscription_id 定位
- update 可部分更新（只传改的字段）
- pause/resume 切 enabled 标志
- delete 级联删除 company + subscription + matches（含 push_logs 不删，留作审计）
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import select

from python.models import Company, Match, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)


async def _find_subscription(session, *, company_id: Optional[int], subscription_id: Optional[int]) -> Optional[Subscription]:
    """按 company_id 或 subscription_id 查 subscription。"""
    if subscription_id:
        stmt = select(Subscription).where(Subscription.id == subscription_id)
    elif company_id:
        stmt = select(Subscription).where(Subscription.company_id == company_id)
    else:
        return None
    return (await session.execute(stmt)).scalar_one_or_none()


async def handle_update_subscription(arguments: dict) -> list[dict]:
    """update_subscription：部分更新订阅字段。"""
    company_id = arguments.get("company_id")
    subscription_id = arguments.get("subscription_id")
    if not company_id and not subscription_id:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "company_id or subscription_id required"},
                ensure_ascii=False,
            ),
        }]

    # 可更新字段
    updatable = {
        "types": arguments.get("types"),
        "regions": arguments.get("regions"),
        "keywords": arguments.get("keywords"),
        "push_schedule": arguments.get("push_schedule"),
        "push_time": arguments.get("push_time"),
        "webhook_url": arguments.get("webhook_url"),
        "platform_hint": arguments.get("platform_hint"),
    }
    # 过滤 None
    updates = {k: v for k, v in updatable.items() if v is not None}
    if not updates:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "no fields to update"},
                ensure_ascii=False,
            ),
        }]

    async with get_session() as session:
        sub = await _find_subscription(session, company_id=company_id, subscription_id=subscription_id)
        if sub is None:
            return [{
                "type": "text",
                "text": json.dumps(
                    {"status": "error", "error": "subscription not found"},
                    ensure_ascii=False,
                ),
            }]
        for k, v in updates.items():
            setattr(sub, k, v)
        return [{
            "type": "text",
            "text": json.dumps({
                "status": "ok",
                "subscription_id": sub.id,
                "company_id": sub.company_id,
                "updated_fields": list(updates.keys()),
                "message": f"订阅已更新（{len(updates)} 个字段）",
            }, ensure_ascii=False),
        }]


async def handle_pause_subscription(arguments: dict) -> list[dict]:
    """pause_subscription：enabled=False，定时推送跳过。"""
    return await _set_enabled(arguments, enabled=False, action="暂停")


async def handle_resume_subscription(arguments: dict) -> list[dict]:
    """resume_subscription：enabled=True。"""
    return await _set_enabled(arguments, enabled=True, action="恢复")


async def _set_enabled(arguments: dict, *, enabled: bool, action: str) -> list[dict]:
    company_id = arguments.get("company_id")
    subscription_id = arguments.get("subscription_id")
    if not company_id and not subscription_id:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "company_id or subscription_id required"},
                ensure_ascii=False,
            ),
        }]
    async with get_session() as session:
        sub = await _find_subscription(session, company_id=company_id, subscription_id=subscription_id)
        if sub is None:
            return [{
                "type": "text",
                "text": json.dumps(
                    {"status": "error", "error": "subscription not found"},
                    ensure_ascii=False,
                ),
            }]
        sub.enabled = enabled
        return [{
            "type": "text",
            "text": json.dumps({
                "status": "ok",
                "subscription_id": sub.id,
                "company_id": sub.company_id,
                "enabled": enabled,
                "message": f"订阅已{action}",
            }, ensure_ascii=False),
        }]


async def handle_delete_subscription(arguments: dict) -> list[dict]:
    """delete_subscription：删除公司 + 订阅 + matches（级联）。

    注意：push_logs 不删（虽然没外键，是独立审计）。
    """
    company_id = arguments.get("company_id")
    subscription_id = arguments.get("subscription_id")
    if not company_id and not subscription_id:
        return [{
            "type": "text",
            "text": json.dumps(
                {"status": "error", "error": "company_id or subscription_id required"},
                ensure_ascii=False,
            ),
        }]

    async with get_session() as session:
        sub = await _find_subscription(session, company_id=company_id, subscription_id=subscription_id)
        if sub is None:
            return [{
                "type": "text",
                "text": json.dumps(
                    {"status": "error", "error": "subscription not found"},
                    ensure_ascii=False,
                ),
            }]

        comp_id = sub.company_id
        sub_id = sub.id

        # 删 matches（级联已配，但显式更清晰）
        match_stmt = select(Match).where(Match.subscription_id == sub_id)
        matches_to_delete = list((await session.execute(match_stmt)).scalars().all())
        for m in matches_to_delete:
            await session.delete(m)

        # 删 subscription（cascade 删 matches 双保险）
        await session.delete(sub)
        # 删 company
        comp_stmt = select(Company).where(Company.id == comp_id)
        comp = (await session.execute(comp_stmt)).scalar_one_or_none()
        if comp:
            await session.delete(comp)

    return [{
        "type": "text",
        "text": json.dumps({
            "status": "ok",
            "deleted_company_id": comp_id,
            "deleted_subscription_id": sub_id,
            "deleted_matches": len(matches_to_delete),
            "message": f"公司 {comp.name if comp else comp_id} 及其订阅已彻底删除",
        }, ensure_ascii=False),
    }]


async def handle_list_subscriptions(arguments: dict) -> list[dict]:
    """list_subscriptions：列出所有订阅（管理用，可选 filter enabled）。"""
    enabled_only = bool(arguments.get("enabled_only", False))
    async with get_session() as session:
        stmt = select(Subscription)
        if enabled_only:
            stmt = stmt.where(Subscription.enabled.is_(True))
        subs = list((await session.execute(stmt)).scalars().all())
        # 加载 company 关系
        for s in subs:
            await session.refresh(s, ["company"])

    return [{
        "type": "text",
        "text": json.dumps({
            "status": "ok",
            "count": len(subs),
            "subscriptions": [
                {
                    "subscription_id": s.id,
                    "company_id": s.company_id,
                    "company_name": s.company.name if s.company else None,
                    "types": s.types,
                    "regions": s.regions,
                    "push_schedule": s.push_schedule,
                    "webhook_url": s.webhook_url,
                    "enabled": s.enabled,
                    "last_push_at": s.last_push_at.isoformat() if s.last_push_at else None,
                }
                for s in subs
            ],
        }, ensure_ascii=False),
    }]
