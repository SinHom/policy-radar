"""审计日志 API（管理后台用）。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select

from python.app.api.auth import require_admin
from python.models.audit_log import AuditLog
from python.models.base import get_session

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
async def list_audit_logs(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    _user: str = Depends(require_admin),
) -> dict:
    """查审计日志。支持按 actor / action / status 筛选。"""
    async with get_session() as session:
        stmt = select(AuditLog).order_by(desc(AuditLog.id))
        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if status:
            stmt = stmt.where(AuditLog.status == status)
        stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return {
            "logs": [
                {
                    "id": r.id,
                    "actor": r.actor,
                    "action": r.action,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "detail": r.detail[:500],  # 截断防过大
                    "ip": r.ip,
                    "ua": r.ua,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "count": len(rows),
        }


@router.get("/stats")
async def audit_stats(_user: str = Depends(require_admin)) -> dict:
    """审计统计：今日 / 7 天 / 总数。"""
    from sqlalchemy import func
    async with get_session() as session:
        total = (await session.execute(select(func.count(AuditLog.id)))).scalar() or 0
        # 今日
        today = (await session.execute(
            select(func.count(AuditLog.id))
            .where(func.date(AuditLog.created_at) == func.date("now"))
        )).scalar() or 0
        # 按 action 统计
        by_action = (await session.execute(
            select(AuditLog.action, func.count(AuditLog.id).label("c"))
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc())
            .limit(10)
        )).all()
        return {
            "total": total,
            "today": today,
            "by_action": [{"action": r[0], "count": r[1]} for r in by_action],
        }
