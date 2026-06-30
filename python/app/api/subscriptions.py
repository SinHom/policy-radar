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
    regions: Optional[list[str]] = None  # 省级:["北京","广东","浙江"]
    dept_codes: Optional[list[str]] = None  # 部委:["发改委","工信部"] — 与 policy_sources.department 对齐
    city_codes: Optional[list[str]] = None  # 地市:["深圳","杭州"] — 与 policy_sources.region 对齐
    keywords: Optional[list[str]] = None
    enabled: Optional[bool] = None
    # === 多通道推送 ===
    push_channel: Optional[str] = None  # mock / wechat / feishu / wecom / email / webhook
    push_config: Optional[dict] = None  # 渠道特定配置（见 push 模块）


async def _auto_enable_sources(session, regions: list[str], dept_codes: list[str], city_codes: list[str]) -> int:
    """根据订阅选择的 region/dept/city 自动启用对应的 policy_sources。

    匹配规则:source.region 在 regions 或 city_codes,或 source.department 在 dept_codes。
    返回启用的源数。
    """
    from python.models.policy_source import PolicySource
    from sqlalchemy import or_

    conditions = []
    if regions:
        conditions.append(PolicySource.region.in_(regions))
    if city_codes:
        conditions.append(PolicySource.region.in_(city_codes))
    if dept_codes:
        conditions.append(PolicySource.department.in_(dept_codes))
    if not conditions:
        return 0

    stmt = select(PolicySource).where(or_(*conditions))
    rows = (await session.execute(stmt)).scalars().all()
    enabled_count = 0
    for s in rows:
        if not s.enabled:
            s.enabled = True
            enabled_count += 1
    return enabled_count


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
                "dept_codes": s.dept_codes or [],
                "city_codes": s.city_codes or [],
                "keywords": s.keywords or [],
                "webhook_url": s.webhook_url,
                "push_schedule": s.push_schedule,
                "push_time": s.push_time,
                "platform_hint": s.platform_hint,
                "push_channel": s.push_channel,
                "push_config": s.push_config or {},
                "enabled": bool(s.enabled),
                "last_push_at": s.last_push_at.isoformat() if s.last_push_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })
    return {"subscriptions": out, "count": len(out)}


# ===== source 候选清单(给前端多选用) =====

@router.get("/sources/options")
async def list_source_options(_user: str = Depends(require_admin)) -> dict:
    """返回所有 source 的去重 region / department / category 列表,供订阅 modal 多选用。"""
    async with get_session() as session:
        from python.models.policy_source import PolicySource
        rows = (await session.execute(select(PolicySource))).scalars().all()
        regions = set()
        departments = set()
        categories = set()
        for s in rows:
            if s.region:
                regions.add(s.region)
            if s.department:
                departments.add(s.department)
            if s.category:
                categories.add(s.category)
    return {
        "regions": sorted(regions),
        "departments": sorted(departments),
        "categories": sorted(categories),
        "total_sources": len(rows),
    }


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
            # SSRF 防护：校验 webhook_url
            if body.webhook_url:
                import os as _os
                from python.app.security import validate_webhook_url
                allow_private = _os.environ.get("ALLOW_PRIVATE_WEBHOOK") == "1"
                ok, err = validate_webhook_url(body.webhook_url, allow_private=allow_private)
                if not ok:
                    raise HTTPException(status_code=400, detail=f"webhook_url invalid: {err}")
            sub.webhook_url = body.webhook_url or None
        if body.types is not None:
            sub.types = body.types
        if body.regions is not None:
            sub.regions = body.regions
        if body.dept_codes is not None:
            sub.dept_codes = body.dept_codes
        if body.city_codes is not None:
            sub.city_codes = body.city_codes
        if body.keywords is not None:
            sub.keywords = body.keywords
        if body.enabled is not None:
            sub.enabled = body.enabled
        # === 按需启用:用户选了 region/dept/city,自动开对应 source ===
        auto_enabled = 0
        if body.regions is not None or body.dept_codes is not None or body.city_codes is not None:
            auto_enabled = await _auto_enable_sources(
                session,
                body.regions if body.regions is not None else (sub.regions or []),
                body.dept_codes if body.dept_codes is not None else (sub.dept_codes or []),
                body.city_codes if body.city_codes is not None else (sub.city_codes or []),
            )
        if body.push_channel is not None:
            if body.push_channel not in ("mock", "wechat", "feishu", "wecom", "email", "webhook"):
                raise HTTPException(status_code=400, detail=f"invalid push_channel: {body.push_channel}")
            sub.push_channel = body.push_channel
        if body.push_config is not None:
            # SSRF 防护：校验所有 push_config 里的 URL
            import os as _os
            allow_private = _os.environ.get("ALLOW_PRIVATE_WEBHOOK") == "1"
            for k, v in (body.push_config or {}).items():
                if k.endswith("_url") and isinstance(v, str):
                    from python.app.security import validate_webhook_url
                    ok, err = validate_webhook_url(v, allow_private=allow_private)
                    if not ok:
                        raise HTTPException(status_code=400, detail=f"push_config.{k} invalid: {err}")
            sub.push_config = body.push_config
        await session.commit()
    return {
        "ok": True,
        "subscription_id": subscription_id,
        "auto_enabled_sources": auto_enabled,
    }


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
        target_company_id = sub.company_id
        target_company_name = sub.company.name if sub.company else None

    # 构造推送内容 + 调分发器
    from python.app.push.dispatcher import PushContent, dispatch
    push_content = PushContent(
        policy_id=pol.id,
        title=pol.title,
        summary=pol.summary_text or "",
        summary_type=pol.summary_type,
        amount=pol.amount,
        deadline=pol.deadline.isoformat() if pol.deadline else None,
        url=pol.url if pol.url and pol.url.startswith("http") else None,
        source_id=pol.source_id,
        company_id=target_company_id,
        company_name=target_company_name,
    )

    # 决定通道：subscription.push_channel 优先；空则根据历史字段回退
    channel = sub.push_channel or "mock"
    # 兼容旧的 webhook_url：如果 push_channel 是 mock 但 webhook_url 有值，认为是 webhook
    if channel == "mock" and sub.webhook_url and not (sub.push_config or {}).get("webhook_url"):
        channel = "webhook"
        config = {"webhook_url": sub.webhook_url, "secret": sub.webhook_secret}
    else:
        config = sub.push_config or {}

    result = await dispatch(push_content, channel, config)

    # 写日志 + 更新 last_push_at
    async with get_session() as session:
        sub2 = await session.get(Subscription, subscription_id)
        session.add(PushLog(
            policy_id=pol.id,
            target=result.target,
            content=content,
            status="success" if result.ok else "failed",
            error_msg=result.error or "",
        ))
        if sub2 and result.ok:
            sub2.last_push_at = datetime.utcnow()
        await session.commit()

    if not result.ok:
        raise HTTPException(status_code=502, detail=f"{channel} push failed: {result.error}")

    return {
        "ok": True,
        "subscription_id": subscription_id,
        "policy_id": pol.id,
        "policy_title": pol.title,
        "target": result.target,
        "channel": channel,
    }


@router.post("/{subscription_id}/weekly-report")
async def push_weekly_report(
    subscription_id: int,
    slot: str = "weekly",
    _user: str = Depends(require_admin),
) -> dict:
    """生成并推送周报聚合卡片(每周推送一次)。"""
    from python.app.push.daily_report import send_weekly_report as _send
    return await _send(subscription_id, slot=slot)


@router.get("/weekly-report/preview")
async def preview_weekly_report(
    slot: str = "weekly",
    _user: str = Depends(require_admin),
) -> dict:
    """预览周报卡片 JSON(不推送),用于前端展示 / 调试。"""
    from python.app.push.daily_report import build_weekly_report
    cards = await build_weekly_report(slot)
    return {"slot": slot, "card_count": len(cards), "cards": cards}


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


# ===== 渠道测试 =====

@router.post("/test-push")
async def test_push_channel(
    channel: str,
    config: dict,
    _user: str = Depends(require_admin),
) -> dict:
    """测推送渠道是否可用。发一条「测试消息」到指定渠道。

    用法：
    POST /api/subscriptions/test-push?channel=feishu
    body: {"webhook_url":"...","secret":"..."}

    返回：{"ok":true, "channel":"feishu", "target":"...", "error":null}
    """
    from python.app.push.dispatcher import PushContent, dispatch
    test_content = PushContent(
        policy_id=0,
        title="✅ 政策雷达 · 渠道连通测试",
        summary="这是一条来自政策雷达的测试消息。如果您看到这条消息，说明渠道配置正确。",
        summary_type="测试",
        amount=None,
        deadline=None,
        url="http://43.155.161.54:8000/admin",
        source_id="system",
        company_id=0,
        company_name="测试接收方",
    )
    result = await dispatch(test_content, channel, config)
    return {
        "ok": result.ok,
        "channel": result.channel,
        "target": result.target,
        "error": result.error,
    }
