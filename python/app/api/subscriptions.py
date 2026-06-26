"""订阅管理 API（管理后台用）。

端点：
- GET    /api/subscriptions              列出所有订阅（含 company / webhook / 最近推送时间）
- PATCH  /api/subscriptions/{id}         修改订阅（频率/时间/webhook/types/regions/keywords）
- POST   /api/subscriptions/{id}/pause   暂停订阅
- POST   /api/subscriptions/{id}/resume  启用订阅
- POST   /api/subscriptions/{id}/push    手动推送最新政策到该订阅
- DELETE /api/subscriptions/{id}         删除订阅
"""

from __future__ import annotations

import httpx
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from python.app.api.auth import require_admin
from python.app.api.routes import format_push_message
from python.app.config import get_settings
from python.models.base import get_session
from python.models.company import Company
from python.models.policy import Policy
from python.models.push_log import PushLog
from python.models.subscription import Subscription

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


class SubscriptionUpdate(BaseModel):
    """修改订阅字段（全部可选）。"""
    push_schedule: Optional[str] = None  # realtime / daily / weekly / manual
    push_time: Optional[str] = None  # "08:30"
    webhook_url: Optional[str] = None
    types: Optional[list[str]] = None
    regions: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    enabled: Optional[bool] = None


@router.get("")
async def list_subscriptions(_user: str = Depends(require_admin)) -> dict:
    """列出所有订阅，附带最近推送时间。"""
    async with get_session() as session:
        # 用 selectinload 预加载 company，避免 greenlet 错
        subs_q = (
            select(Subscription)
            .options(selectinload(Subscription.company))
            .order_by(Subscription.id.desc())
        )
        subs = (await session.execute(subs_q)).scalars().all()

        out = []
        for s in subs:
            company = s.company
            company_name = company.name if company else f"company#{s.company_id}"
            out.append({
                "subscription_id": s.id,
                "company_id": s.company_id,
                "company_name": company_name,
                "industry": company.industry if company else None,
                "region": company.region if company else None,
                "types": s.types or [],
                "regions": s.regions or [],
                "keywords": s.keywords or [],
                "webhook_url": s.webhook_url,
                "push_schedule": s.push_schedule,
                "push_time": s.push_time,
                "platform_hint": s.platform_hint,
                "enabled": bool(s.enabled),
                "last_push_at": s.last_push_at.isoformat() if s.last_push_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })
    return {"subscriptions": out, "count": len(out)}


@router.patch("/{subscription_id}")
async def update_subscription(
    subscription_id: int,
    body: SubscriptionUpdate,
    _user: str = Depends(require_admin),
) -> dict:
    """修改订阅字段。"""
    async with get_session() as session:
        sub = await session.get(Subscription, subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="subscription not found")
        if body.push_schedule is not None:
            if body.push_schedule not in ("realtime", "daily", "weekly", "manual"):
                raise HTTPException(status_code=400, detail="invalid push_schedule")
            sub.push_schedule = body.push_schedule
        if body.push_time is not None:
            sub.push_time = body.push_time
        if body.webhook_url is not None:
            sub.webhook_url = body.webhook_url or None
        if body.types is not None:
            sub.types = body.types
        if body.regions is not None:
            sub.regions = body.regions
        if body.keywords is not None:
            sub.keywords = body.keywords
        if body.enabled is not None:
            sub.enabled = body.enabled
        await session.commit()
    return {"ok": True, "subscription_id": subscription_id}


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


@router.post("/{subscription_id}/push")
async def manual_push(subscription_id: int, _user: str = Depends(require_admin)) -> dict:
    """手动推送：取最近 1 条已摘要政策，推到该订阅的 webhook（或 mock）。

    用于运营人员测试 webhook 通不通，或临时推送某条政策给某家公司。
    """
    settings = get_settings()

    async with get_session() as session:
        sub = await session.get(Subscription, subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="subscription not found")

        # 找最新一条已摘要政策
        pol = (
            await session.execute(
                select(Policy)
                .where(Policy.summary_text.isnot(None))
                .order_by(Policy.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not pol:
            raise HTTPException(status_code=400, detail="no summarized policy available")

        content = format_push_message(pol)
        target = f"sub-{subscription_id}"

    # 决定推送到哪：webhook_url 优先，否则 mock
    target_url = sub.webhook_url
    if target_url:
        # 推外部 webhook
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    target_url,
                    json={
                        "subscription_id": subscription_id,
                        "policy_id": pol.id,
                        "title": pol.title,
                        "content": content,
                    },
                    headers={"X-Policy-Radar-Source": "manual-push"},
                )
                r.raise_for_status()
        except Exception as e:
            async with get_session() as session:
                session.add(PushLog(
                    policy_id=pol.id,
                    target=target,
                    content=content,
                    status="failed",
                    error_msg=str(e)[:200],
                ))
                await session.commit()
            raise HTTPException(status_code=502, detail=f"webhook push failed: {e}")
    else:
        # 走 mock
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{settings.mock_wechat_url}/sendmessage",
                    json={
                        "context_token": target,
                        "message": {"message_type": 1, "content": content},
                    },
                )
                r.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"mock push failed: {e}")

    # 写日志 + 更新 last_push_at
    async with get_session() as session:
        sub = await session.get(Subscription, subscription_id)
        session.add(PushLog(
            policy_id=pol.id,
            target=target,
            content=content,
            status="success",
        ))
        if sub:
            sub.last_push_at = datetime.utcnow()
        await session.commit()

    return {
        "ok": True,
        "subscription_id": subscription_id,
        "policy_id": pol.id,
        "policy_title": pol.title,
        "target": target,
        "channel": "webhook" if target_url else "mock",
    }


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
