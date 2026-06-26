"""LLM 使用统计 + 配置管理 API（管理后台用）。

端点：
- GET  /api/llm/usage              总体 + 今日统计
- GET  /api/llm/usage?days=7       按天聚合最近 N 天
- GET  /api/llm/usage?by=model     按模型聚合
- GET  /api/llm/usage?limit=50     最近 N 条调用日志
- GET  /api/config/llm             读当前 LLM 配置
- PUT  /api/config/llm             改 LLM 配置（model + base_url + api_key）
- POST /api/config/llm/test         测 LLM 连通性
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from python.app.api.auth import require_admin
from python.models.base import get_session
from python.models.llm_usage_log import LLMUsageLog
from python.models.system_config import SystemConfig

router = APIRouter(prefix="/api", tags=["llm-admin"])


# ===== 统计 =====

@router.get("/llm/usage")
async def get_llm_usage(
    days: int = 7,
    by: Optional[str] = None,  # None / "model" / "purpose" / "day"
    limit: int = 0,  # > 0 = 返回原始日志
    _user: str = Depends(require_admin),
) -> dict:
    """LLM token 消耗统计。

    by=None  →  总体统计（按 day 聚合，days 参数生效）
    by=model →  按 model 聚合
    by=purpose → 按 purpose 聚合
    limit>0  →  返回最近 N 条原始日志
    """
    async with get_session() as session:
        if limit > 0:
            stmt = select(LLMUsageLog).order_by(desc(LLMUsageLog.id)).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return {
                "logs": [
                    {
                        "id": r.id,
                        "model": r.model,
                        "input_tokens": r.input_tokens,
                        "output_tokens": r.output_tokens,
                        "total_tokens": r.total_tokens,
                        "purpose": r.purpose,
                        "policy_id": r.policy_id,
                        "status": r.status,
                        "duration_ms": r.duration_ms,
                        "error_msg": r.error_msg,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        if by in (None, "day"):
            # 按天聚合
            stmt = (
                select(
                    func.date(LLMUsageLog.created_at).label("day"),
                    func.sum(LLMUsageLog.input_tokens).label("in_tok"),
                    func.sum(LLMUsageLog.output_tokens).label("out_tok"),
                    func.count(LLMUsageLog.id).label("calls"),
                )
                .where(LLMUsageLog.created_at >= func.datetime("now", f"-{days} day"))
                .group_by(func.date(LLMUsageLog.created_at))
                .order_by(func.date(LLMUsageLog.created_at).desc())
            )
            rows = (await session.execute(stmt)).all()
            daily = [
                {
                    "day": str(r.day),
                    "input_tokens": r.in_tok or 0,
                    "output_tokens": r.out_tok or 0,
                    "total_tokens": (r.in_tok or 0) + (r.out_tok or 0),
                    "calls": r.calls or 0,
                }
                for r in rows
            ]
            # 总体
            total_in = sum(d["input_tokens"] for d in daily)
            total_out = sum(d["output_tokens"] for d in daily)
            return {
                "period_days": days,
                "total": {
                    "input_tokens": total_in,
                    "output_tokens": total_out,
                    "total_tokens": total_in + total_out,
                    "calls": sum(d["calls"] for d in daily),
                },
                "daily": daily,
            }
        elif by in ("model", "purpose"):
            col = LLMUsageLog.model if by == "model" else LLMUsageLog.purpose
            stmt = (
                select(
                    col.label("key"),
                    func.sum(LLMUsageLog.input_tokens).label("in_tok"),
                    func.sum(LLMUsageLog.output_tokens).label("out_tok"),
                    func.count(LLMUsageLog.id).label("calls"),
                )
                .where(LLMUsageLog.created_at >= func.datetime("now", f"-{days} day"))
                .group_by(col)
                .order_by(func.count(LLMUsageLog.id).desc())
            )
            rows = (await session.execute(stmt)).all()
            return {
                "by": by,
                "period_days": days,
                "groups": [
                    {
                        "key": r.key,
                        "input_tokens": r.in_tok or 0,
                        "output_tokens": r.out_tok or 0,
                        "total_tokens": (r.in_tok or 0) + (r.out_tok or 0),
                        "calls": r.calls or 0,
                    }
                    for r in rows
                ],
            }
        else:
            raise HTTPException(status_code=400, detail=f"invalid by: {by}")


# ===== 配置管理 =====

class LLMConfig(BaseModel):
    """LLM 配置。"""
    model: str
    base_url: str
    api_key: str  # 读写时脱敏显示


class LLMConfigUpdate(BaseModel):
    """修改 LLM 配置（全部可选）。"""
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


def _mask_key(k: str) -> str:
    """脱敏显示 API key：前 4 + ... + 后 4"""
    if not k or len(k) < 8:
        return "***"
    return f"{k[:4]}...{k[-4:]}"


@router.get("/config/llm")
async def get_llm_config(_user: str = Depends(require_admin)) -> dict:
    """读当前 LLM 配置。"""
    async with get_session() as session:
        cfg = await SystemConfig.get(session, "llm", default={})
    return {
        "model": cfg.get("model") or os.environ.get("MINIMAX_MODEL", "MiniMax-M3"),
        "base_url": cfg.get("base_url") or os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"),
        "api_key": _mask_key(cfg.get("api_key") or os.environ.get("MINIMAX_API_KEY", "")),
        "api_key_set": bool(cfg.get("api_key") or os.environ.get("MINIMAX_API_KEY")),
        "source": "db" if cfg else "env",  # 提示来自 DB 还是 env
    }


@router.put("/config/llm")
async def update_llm_config(
    body: LLMConfigUpdate,
    _user: str = Depends(require_admin),
) -> dict:
    """改 LLM 配置（DB）。改了立即生效（下次 LLM 调用读新配置）。"""
    async with get_session() as session:
        cfg = await SystemConfig.get(session, "llm", default={})
        if body.model is not None:
            cfg["model"] = body.model
        if body.base_url is not None:
            cfg["base_url"] = body.base_url
        if body.api_key is not None and body.api_key != "":
            cfg["api_key"] = body.api_key
        await SystemConfig.set(session, "llm", cfg)
    return {"ok": True, "source": "db"}


@router.post("/config/llm/test")
async def test_llm_config(_user: str = Depends(require_admin)) -> dict:
    """测当前 LLM 配置是否可用。发最小请求。"""
    from python.ai.llm_client import LLMClient
    try:
        async with get_session() as session:
            cfg = await SystemConfig.get(session, "llm", default={})
        # 临时 client 测
        client = LLMClient(
            base_url=cfg.get("base_url") or None,
            api_key=cfg.get("api_key") or None,
            model=cfg.get("model") or None,
        )
        ok = await client.health_check()
        return {"ok": ok, "model": client.model, "base_url": client.base_url}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
