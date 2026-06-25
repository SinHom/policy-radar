"""Dashboard API：漏斗统计 + 推送历史查询。

漏斗（从推送 → 查看 → 咨询）：
- push:        push_logs 表 status=success 的总条数
- clicked:     暂时没有"用户点击"埋点，用 matches.pushed=True 推算（推送出去 = 算触达）
- consulted:   暂时没 consultations 表，placeholder = 0

P2-4 范围：
- /api/dashboard/funnel: 返回漏斗
- /api/push-history: 按 company_id / date range 查推送历史
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, desc, func, select

from python.models import Company, Match, Policy, PushLog, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dashboard/funnel")
async def dashboard_funnel(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
) -> dict:
    """漏斗：推送 → 触达 → 咨询。

    当前数据：
    - push:  push_logs.status='success' 计数
    - reached: matches.pushed=True 计数（推送出去 = 用户触达）
    - consulted: 暂未实现 consultations 表，固定返回 0
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with get_session() as session:
        # 推送次数（push_logs）
        push_count = (await session.execute(
            select(func.count(PushLog.id))
            .where(PushLog.created_at >= cutoff)
            .where(PushLog.status == "success")
        )).scalar() or 0
        # 推送失败次数
        push_fail = (await session.execute(
            select(func.count(PushLog.id))
            .where(PushLog.created_at >= cutoff)
            .where(PushLog.status == "failed")
        )).scalar() or 0
        # 触达（matches.pushed = True）
        reached = (await session.execute(
            select(func.count(Match.id))
            .where(Match.pushed.is_(True))
            .where(Match.pushed_at >= cutoff)
        )).scalar() or 0
        # 咨询（暂未实现）
        consulted = 0

    funnel = [
        {"stage": "推送", "count": push_count},
        {"stage": "触达", "count": reached},
        {"stage": "咨询", "count": consulted},
    ]
    return {
        "days": days,
        "funnel": funnel,
        "stats": {
            "push_success": push_count,
            "push_failed": push_fail,
            "push_success_rate": (
                push_count / (push_count + push_fail) if (push_count + push_fail) > 0 else 0
            ),
            "reached": reached,
            "consulted": consulted,
        },
        "note": "consulted 阶段需后续埋点（用户咨询事件）",
    }


@router.get("/push-history")
async def push_history(
    company_id: Optional[int] = None,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """推送历史：按 company_id / 时间范围 / limit 查。"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with get_session() as session:
        stmt = (
            select(PushLog, Policy, Subscription)
            .outerjoin(Policy, PushLog.policy_id == Policy.id)
            .outerjoin(Subscription, PushLog.id == Subscription.id)  # 不关联（push_log 没 sub_id）
        )
        # 注：push_logs 表没有 subscription_id 字段，只能按 content JSON 过滤
        # 这里简化：只按 time 过滤
        if company_id is not None:
            # content 包含 "company_id": company_id
            stmt = stmt.where(PushLog.content.like(f'%"company_id": {company_id}%'))
        stmt = stmt.where(PushLog.created_at >= cutoff)
        stmt = stmt.order_by(desc(PushLog.created_at)).limit(limit)
        rows = list((await session.execute(stmt)).all())

    items = []
    for log, pol, sub in rows:
        items.append({
            "id": log.id,
            "policy_id": log.policy_id,
            "policy_title": pol.title if pol else None,
            "target": log.target,
            "status": log.status,
            "error_msg": log.error_msg,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "content_preview": (log.content or "")[:200],
        })

    return {
        "company_id": company_id,
        "days": days,
        "count": len(items),
        "items": items,
    }


@router.get("/dashboard/companies")
async def dashboard_companies() -> dict:
    """企业汇总：每个企业的订阅/匹配/推送数。"""
    async with get_session() as session:
        stmt = (
            select(
                Company.id,
                Company.name,
                Company.industry,
                Company.region,
                func.count(func.distinct(Subscription.id)).label("subs"),
                func.count(func.distinct(Match.id)).label("matches"),
                func.sum(
                    func.iif(Match.pushed.is_(True), 1, 0)
                ).label("pushed"),
            )
            .outerjoin(Subscription, Subscription.company_id == Company.id)
            .outerjoin(Match, Match.subscription_id == Subscription.id)
            .group_by(Company.id)
        )
        rows = list((await session.execute(stmt)).all())

    return {
        "count": len(rows),
        "companies": [
            {
                "company_id": r[0],
                "name": r[1],
                "industry": r[2],
                "region": r[3],
                "subscriptions": r[4] or 0,
                "matches": r[5] or 0,
                "pushed": int(r[6] or 0),
            }
            for r in rows
        ],
    }
