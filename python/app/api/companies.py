"""公司档案管理 API（管理后台用）。

端点：
- GET    /api/companies                  列出所有公司（含订阅状态、匹配数、推送数）
- PATCH  /api/companies/{id}             修改公司信息（name/industry/region/scale/tags）
- POST   /api/companies                  新建公司（可选同时建订阅）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from python.app.api.auth import require_admin
from python.models.base import get_session
from python.models.company import Company
from python.models.subscription import Subscription

router = APIRouter(prefix="/api/companies", tags=["companies"])


class CompanyUpdate(BaseModel):
    """修改公司字段（全部可选）。"""
    name: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    scale: Optional[str] = None
    tags: Optional[list[str]] = None


class CompanyCreate(BaseModel):
    """新建公司。"""
    name: str
    industry: Optional[str] = None
    region: Optional[str] = None
    scale: Optional[str] = None
    tags: Optional[list[str]] = None
    # 可选：同时建订阅
    push_schedule: str = "daily"  # realtime / daily / weekly / manual
    push_time: str = "08:30"
    webhook_url: Optional[str] = None
    types: list[str] = []
    regions: list[str] = []
    keywords: Optional[list[str]] = None


class CompanyOut(BaseModel):
    id: int
    name: str
    industry: Optional[str] = None
    region: Optional[str] = None
    scale: Optional[str] = None
    tags: Optional[list] = None
    has_subscription: bool = False
    push_schedule: Optional[str] = None
    push_time: Optional[str] = None
    enabled: Optional[bool] = None
    last_push_at: Optional[str] = None
    created_at: Optional[str] = None


@router.get("", response_model=list[CompanyOut])
async def list_companies(_user: str = Depends(require_admin)) -> list[CompanyOut]:
    """列出所有公司 + 订阅信息。"""
    async with get_session() as session:
        companies = (
            await session.execute(select(Company).order_by(Company.id.desc()))
        ).scalars().all()
        out = []
        for c in companies:
            sub = c.subscription
            out.append(CompanyOut(
                id=c.id,
                name=c.name,
                industry=c.industry,
                region=c.region,
                scale=c.scale,
                tags=c.tags or [],
                has_subscription=sub is not None,
                push_schedule=sub.push_schedule if sub else None,
                push_time=sub.push_time if sub else None,
                enabled=sub.enabled if sub else None,
                last_push_at=sub.last_push_at.isoformat() if sub and sub.last_push_at else None,
                created_at=c.created_at.isoformat() if c.created_at else None,
            ))
    return out


@router.patch("/{company_id}")
async def update_company(
    company_id: int,
    body: CompanyUpdate,
    _user: str = Depends(require_admin),
) -> dict:
    """修改公司字段。"""
    async with get_session() as session:
        c = await session.get(Company, company_id)
        if not c:
            raise HTTPException(status_code=404, detail="company not found")
        if body.name is not None:
            c.name = body.name
        if body.industry is not None:
            c.industry = body.industry
        if body.region is not None:
            c.region = body.region
        if body.scale is not None:
            c.scale = body.scale
        if body.tags is not None:
            c.tags = body.tags
        await session.commit()
    return {"ok": True, "company_id": company_id}


@router.post("")
async def create_company(
    body: CompanyCreate,
    _user: str = Depends(require_admin),
) -> dict:
    """新建公司（可选同时建订阅）。"""
    async with get_session() as session:
        c = Company(
            name=body.name,
            industry=body.industry,
            region=body.region,
            scale=body.scale,
            tags=body.tags or [],
        )
        session.add(c)
        await session.flush()  # 拿到 c.id

        # 同时建订阅
        if body.push_schedule or body.webhook_url or body.types or body.regions:
            sub = Subscription(
                company_id=c.id,
                push_schedule=body.push_schedule,
                push_time=body.push_time,
                webhook_url=body.webhook_url,
                types=body.types or [],
                regions=body.regions or [],
                keywords=body.keywords,
                enabled=True,
            )
            session.add(sub)
        await session.commit()
    return {"ok": True, "company_id": c.id, "name": c.name}
