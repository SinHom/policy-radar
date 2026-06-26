"""订阅管理 API（管理后台用）。

端点：
- GET    /api/subscriptions          列出所有订阅（含 company / webhook / 最近推送时间）
- POST   /api/subscriptions/{id}/pause   暂停订阅
- POST   /api/subscriptions/{id}/resume  启用订阅
- DELETE /api/subscriptions/{id}         删除订阅
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from python.app.api.auth import require_admin
from python.models.base import get_session
from python.models.subscription import Subscription

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


@router.get("")
async def list_subscriptions(_user: str = Depends(require_admin)) -> dict:
    """列出所有订阅，附带最近推送时间（通过 company_id → policy_id → push_logs 关联推算）。"""
    async with get_session() as session:
        subs_q = select(Subscription).order_by(Subscription.id.desc())
        subs = (await session.execute(subs_q)).scalars().all()

        out = []
        for s in subs:
            out.append({
                "subscription_id": s.id,
                "company_id": s.company_id,
                "company_name": s.company_name,
                "industry": getattr(s, "industry", None),
                "region": getattr(s, "region", None),
                "types": getattr(s, "types", []) or [],
                "regions": getattr(s, "regions", []) or [],
                "webhook_url": s.webhook_url,
                "push_schedule": getattr(s, "push_schedule", "daily"),
                "enabled": bool(s.enabled),
                "last_push_at": None,  # TODO: 通过 company_id 关联算
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })
    return {"subscriptions": out, "count": len(out)}


@router.post("/{subscription_id}/pause")
async def pause_subscription(subscription_id: int, _user: str = Depends(require_admin)) -> dict:
    """暂停订阅。"""
    async with get_session() as session:
        sub = await session.get(Subscription, subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="subscription not found")
        sub.enabled = False
        await session.commit()
    return {"ok": True, "subscription_id": subscription_id, "enabled": False}


@router.post("/{subscription_id}/resume")
async def resume_subscription(subscription_id: int, _user: str = Depends(require_admin)) -> dict:
    """启用订阅。"""
    async with get_session() as session:
        sub = await session.get(Subscription, subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="subscription not found")
        sub.enabled = True
        await session.commit()
    return {"ok": True, "subscription_id": subscription_id, "enabled": True}


@router.delete("/{subscription_id}")
async def delete_subscription(subscription_id: int, _user: str = Depends(require_admin)) -> dict:
    """删除订阅（关联推送日志按 policy_id CASCADE 由 DB 处理）。"""
    async with get_session() as session:
        sub = await session.get(Subscription, subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="subscription not found")
        await session.delete(sub)
        await session.commit()
    return {"ok": True, "subscription_id": subscription_id, "deleted": True}
