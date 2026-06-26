"""政策源管理 API（管理后台用）。

端点：
- PATCH /api/sources/{id}   修改源（启用/停用、改名、调频率等）
- POST   /api/sources       新建源
- DELETE /api/sources/{id}  删除源（级联删 policies + push_logs）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from python.app.api.auth import require_admin
from python.models.base import get_session
from python.models.policy_source import PolicySource

router = APIRouter(prefix="/api/sources", tags=["sources-admin"])


class SourceUpdate(BaseModel):
    """修改源字段（全部可选）。"""
    name: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    spider_config: Optional[dict] = None
    frequency: Optional[str] = None  # realtime / daily / weekly
    enabled: Optional[bool] = None


class SourceCreate(BaseModel):
    """新建源。"""
    source_id: str
    name: str
    url: Optional[str] = None
    category: Optional[str] = None
    spider_config: dict = {}
    frequency: str = "daily"
    enabled: bool = True


@router.patch("/{source_id_db}")
async def update_source(
    source_id_db: int,
    body: SourceUpdate,
    _user: str = Depends(require_admin),
) -> dict:
    """修改源。"""
    async with get_session() as session:
        src = await session.get(PolicySource, source_id_db)
        if not src:
            raise HTTPException(status_code=404, detail="source not found")
        if body.name is not None:
            src.name = body.name
        if body.url is not None:
            src.url = body.url
        if body.category is not None:
            src.category = body.category
        if body.spider_config is not None:
            src.spider_config = body.spider_config
        if body.frequency is not None:
            src.frequency = body.frequency
        if body.enabled is not None:
            src.enabled = body.enabled
        await session.commit()
    return {"ok": True, "source_id_db": source_id_db}


@router.post("")
async def create_source(
    body: SourceCreate,
    _user: str = Depends(require_admin),
) -> dict:
    """新建源。"""
    async with get_session() as session:
        # 查重
        existing = (await session.execute(
            select(PolicySource).where(PolicySource.source_id == body.source_id)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail=f"source_id '{body.source_id}' 已存在")
        src = PolicySource(
            source_id=body.source_id,
            name=body.name,
            url=body.url,
            category=body.category,
            spider_config=body.spider_config,
            frequency=body.frequency,
            enabled=body.enabled,
        )
        session.add(src)
        await session.commit()
    return {"ok": True, "source_id": body.source_id}


@router.delete("/{source_id_db}")
async def delete_source(
    source_id_db: int,
    _user: str = Depends(require_admin),
) -> dict:
    """删除源（级联删 policies + push_logs）。"""
    async with get_session() as session:
        src = await session.get(PolicySource, source_id_db)
        if not src:
            raise HTTPException(status_code=404, detail="source not found")
        await session.delete(src)
        await session.commit()
    return {"ok": True, "source_id_db": source_id_db, "deleted": True}
