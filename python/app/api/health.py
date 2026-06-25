"""健康检查 / 指标端点（生产化必备）。

- /health:    简单探活（DB 可达 + scheduler 状态）
- /metrics:   Prometheus 文本格式（policy 数、match 数、push 成功率、LLM 失败率）
- /version:   服务版本 + 关键依赖版本
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from python.models import Company, Match, Policy, PushDeadLetter, PushLog, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    """健康检查：DB 可达 + 基础统计。"""
    try:
        async with get_session() as session:
            # DB 探活
            db_ok = True
            db_error = None
            try:
                await session.execute(select(1))
            except Exception as e:
                db_ok = False
                db_error = str(e)

            # 统计
            policies_count = (await session.execute(select(func.count(Policy.id)))).scalar() or 0
            summarized = (await session.execute(
                select(func.count(Policy.id)).where(Policy.summary_text.isnot(None))
            )).scalar() or 0
            companies = (await session.execute(select(func.count(Company.id)))).scalar() or 0
            subs = (await session.execute(select(func.count(Subscription.id)))).scalar() or 0
            enabled_subs = (await session.execute(
                select(func.count(Subscription.id)).where(Subscription.enabled.is_(True))
            )).scalar() or 0
            unresolved_dead = (await session.execute(
                select(func.count(PushDeadLetter.id)).where(PushDeadLetter.resolved.is_(False))
            )).scalar() or 0

        status = "ok" if db_ok else "degraded"
        return {
            "status": status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "db": {"ok": db_ok, "error": db_error},
            "stats": {
                "policies_total": policies_count,
                "policies_summarized": summarized,
                "companies": companies,
                "subscriptions": subs,
                "subscriptions_enabled": enabled_subs,
                "dead_letters_unresolved": unresolved_dead,
            },
        }
    except Exception as e:
        logger.exception("health check failed")
        return {"status": "error", "error": str(e)}


@router.get("/metrics")
async def metrics() -> str:
    """Prometheus 文本格式指标。"""
    lines: list[str] = []
    async with get_session() as session:
        # 简单计数
        for name, stmt in [
            ("policy_radar_policies_total", select(func.count(Policy.id))),
            ("policy_radar_policies_summarized", select(func.count(Policy.id)).where(Policy.summary_text.isnot(None))),
            ("policy_radar_companies_total", select(func.count(Company.id))),
            ("policy_radar_subscriptions_total", select(func.count(Subscription.id))),
            ("policy_radar_subscriptions_enabled", select(func.count(Subscription.id)).where(Subscription.enabled.is_(True))),
            ("policy_radar_matches_total", select(func.count(Match.id))),
            ("policy_radar_matches_pushed", select(func.count(Match.id)).where(Match.pushed.is_(True))),
            ("policy_radar_dead_letters_unresolved", select(func.count(PushDeadLetter.id)).where(PushDeadLetter.resolved.is_(False))),
            ("policy_radar_dead_letters_resolved", select(func.count(PushDeadLetter.id)).where(PushDeadLetter.resolved.is_(True))),
        ]:
            val = (await session.execute(stmt)).scalar() or 0
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {val}")

        # 最近 24h 推送成功率
        cutoff = datetime.utcnow() - timedelta(hours=24)
        push_total = (await session.execute(
            select(func.count(PushLog.id)).where(PushLog.created_at >= cutoff)
        )).scalar() or 0
        push_success = (await session.execute(
            select(func.count(PushLog.id))
            .where(PushLog.created_at >= cutoff)
            .where(PushLog.status == "success")
        )).scalar() or 0
        lines.append("# TYPE policy_radar_push_total_24h counter")
        lines.append(f"policy_radar_push_total_24h {push_total}")
        lines.append("# TYPE policy_radar_push_success_24h counter")
        lines.append(f"policy_radar_push_success_24h {push_success}")
        if push_total > 0:
            success_rate = push_success / push_total
            lines.append("# TYPE policy_radar_push_success_rate_24h gauge")
            lines.append(f"policy_radar_push_success_rate_24h {success_rate:.4f}")

        # 最近 7 天新政策
        cutoff_7d = datetime.utcnow() - timedelta(days=7)
        new_7d = (await session.execute(
            select(func.count(Policy.id)).where(Policy.crawled_at >= cutoff_7d)
        )).scalar() or 0
        lines.append("# TYPE policy_radar_policies_crawled_7d counter")
        lines.append(f"policy_radar_policies_crawled_7d {new_7d}")

    return "\n".join(lines) + "\n"


@router.get("/version")
async def version() -> dict:
    """服务版本。"""
    import fastapi
    import sqlalchemy
    mcp_version = "unknown"
    try:
        import mcp
        mcp_version = getattr(mcp, "__version__", "unknown")
    except Exception:
        pass
    return {
        "service": "policy-radar",
        "version": "0.2.0",  # MCP 化后版本
        "mcp_tools": 13,
        "deps": {
            "fastapi": fastapi.__version__,
            "sqlalchemy": sqlalchemy.__version__,
            "mcp": mcp_version,
        },
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
