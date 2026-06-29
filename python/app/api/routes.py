"""业务 API 路由（MVP：4 个核心端点 + 推送日志）。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
from collections import Counter

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select

from python.ai.summarizer import summarize_one
from python.app.config import get_settings
from python.crawlers.engine import crawl_source, run_crawler
from python.models import Policy, PolicySource, PushLog
from python.models.base import get_session

logger = logging.getLogger(__name__)

router = APIRouter()


# === 数据模型 ===

class CrawlResultOut(BaseModel):
    source_id: str
    total_listed: int
    new_crawled: int
    skipped_duplicate: int
    errors: int
    error_messages: list[str] = []


class PolicyOut(BaseModel):
    id: int
    title: str
    url: str
    source_id: str
    summary_type: Optional[str] = None
    summary_text: Optional[str] = None
    amount: Optional[str] = None
    deadline: Optional[str] = None
    keywords: list[str] = []
    published_at: Optional[str] = None
    summarized_at: Optional[str] = None


class PushResultOut(BaseModel):
    ok: bool
    policy_id: int
    target: str
    content: str
    error: Optional[str] = None


class PushLogOut(BaseModel):
    id: int
    policy_id: int
    target: str
    content: str
    status: str
    error_msg: Optional[str] = None
    created_at: str


# === 端点 ===

@router.get("/sources")
async def list_sources(tag: str = None, region: str = None, category: str = None):
    """列出政策源。支持按 tag/region/category 筛选（任一为空则不过滤）。"""
    async with get_session() as session:
        stmt = select(PolicySource).order_by(PolicySource.id)
        rows = (await session.execute(stmt)).scalars().all()
        out = []
        for s in rows:
            tags = s.tags or []
            if tag and tag not in tags and tag not in (s.category or ""):
                continue
            if region and region != s.region:
                continue
            if category and category != s.category:
                continue
            out.append({
                "id": s.id,
                "source_id": s.source_id,
                "name": s.name,
                "url": s.url,
                "category": s.category,
                "region": s.region,
                "department": s.department,
                "tags": tags,
                "frequency": s.frequency,
                "enabled": s.enabled,
                "last_crawl_at": s.last_crawl_at.isoformat() if s.last_crawl_at else None,
                "last_status": s.last_status,
            })
        return out


@router.post("/crawl/all", response_model=list[CrawlResultOut])
async def crawl_all():
    """爬取所有 enabled 源。"""
    results = await run_crawler()
    return [
        CrawlResultOut(
            source_id=r.source_id,
            total_listed=r.total_listed,
            new_crawled=r.new_crawled,
            skipped_duplicate=r.skipped_duplicate,
            errors=r.errors,
            error_messages=r.error_messages[:3],
        )
        for r in results
    ]


@router.post("/crawl/{source_id}", response_model=CrawlResultOut)
async def crawl_one(source_id: str):
    """爬取单个源。"""
    r = await crawl_source(source_id)
    return CrawlResultOut(
        source_id=r.source_id,
        total_listed=r.total_listed,
        new_crawled=r.new_crawled,
        skipped_duplicate=r.skipped_duplicate,
        errors=r.errors,
        error_messages=r.error_messages[:3],
    )


@router.get("/policies", response_model=list[PolicyOut])
async def list_policies(limit: int = 50, summarized_only: bool = True):
    """列出政策。summarized_only=True 时只返回已摘要的。"""
    async with get_session() as session:
        stmt = select(Policy).order_by(desc(Policy.id)).limit(limit)
        if summarized_only:
            stmt = stmt.where(Policy.summary_text.isnot(None))
        rows = (await session.execute(stmt)).scalars().all()
        # 取 source_id 映射
        src_stmt = select(PolicySource)
        src_rows = (await session.execute(src_stmt)).scalars().all()
        src_map = {s.id: s.source_id for s in src_rows}

        return [
            PolicyOut(
                id=p.id,
                title=p.title,
                url=p.url,
                source_id=src_map.get(p.source_id, "?"),
                summary_type=p.summary_type,
                summary_text=p.summary_text,
                amount=(p.summary_data or {}).get("amount") if p.summary_data else None,
                deadline=(p.summary_data or {}).get("deadline") if p.summary_data else None,
                keywords=(p.summary_data or {}).get("keywords", []) if p.summary_data else [],
                published_at=p.published_at.isoformat() if p.published_at else None,
                summarized_at=p.summarized_at.isoformat() if p.summarized_at else None,
            )
            for p in rows
        ]


@router.post("/policies/{policy_id}/summarize")
async def summarize_one_endpoint(policy_id: int):
    """手动摘要单条政策。"""
    try:
        data = await summarize_one(policy_id)
        return {"ok": True, "policy_id": policy_id, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarize failed: {e}")


@router.post("/policies/{policy_id}/push", response_model=PushResultOut)
async def push_policy(policy_id: int, target: str = "mock-ctx-default"):
    """推送单条政策到 Mock 微信。"""
    settings = get_settings()

    # 查 policy
    async with get_session() as session:
        stmt = select(Policy).where(Policy.id == policy_id)
        pol = (await session.execute(stmt)).scalar_one_or_none()
        if pol is None:
            raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
        if not pol.summary_text:
            raise HTTPException(status_code=400, detail="Policy not summarized yet")
        # 格式化推送内容
        content = format_push_message(pol)
        title = pol.title

    # 调 mock_wechat /sendmessage
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
        # 失败也写日志
        async with get_session() as session:
            session.add(PushLog(
                policy_id=policy_id,
                target=target,
                content=content,
                status="failed",
                error_msg=str(e),
            ))
        raise HTTPException(status_code=502, detail=f"Push failed: {e}")

    # 写 push_log
    async with get_session() as session:
        session.add(PushLog(
            policy_id=policy_id,
            target=target,
            content=content,
            status="success",
        ))

    return PushResultOut(ok=True, policy_id=policy_id, target=target, content=content)


@router.get("/push-logs", response_model=list[PushLogOut])
async def list_push_logs(limit: int = 30, target: str = None):
    """列推送日志。可按 target 过滤（'sub-{id}' = 单订阅，'mock-ctx-default' = mock）。"""
    async with get_session() as session:
        stmt = select(PushLog).order_by(desc(PushLog.id))
        if target:
            stmt = stmt.where(PushLog.target == target)
        stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            PushLogOut(
                id=r.id,
                policy_id=r.policy_id,
                target=r.target,
                content=r.content,
                status=r.status,
                error_msg=r.error_msg,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ]


# === 工具函数 ===

def format_push_message(pol: Policy) -> str:
    """格式化推送内容（参考 demo 风格）。"""
    lines = [
        "📡 政策雷达 · 推送",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "━━━━━━━━━━━━━━━",
        f"🏷 {pol.summary_type or '其他'}",
        pol.title,
    ]
    if pol.summary_text:
        lines.append(f"📝 {pol.summary_text}")
    data = pol.summary_data or {}
    if data.get("amount"):
        lines.append(f"💰 {data['amount']}")
    if data.get("deadline"):
        lines.append(f"⏰ 截止 {data['deadline']}")
    if data.get("target_enterprise"):
        lines.append(f"🎯 面向: {data['target_enterprise']}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"🔗 {pol.url[:80]}")
    return "\n".join(lines)


# === 前端多维筛选 endpoint(sidebar 用) ===

class PolicyWithSourceOut(BaseModel):
    """多维筛选返回的 policy,带 source 元数据(region/department/category)
    让前端 sidebar 显示筛选项时不需额外请求。"""
    id: int
    title: str
    url: str
    source_id: str
    region: Optional[str] = None
    department: Optional[str] = None
    category: Optional[str] = None
    summary_type: Optional[str] = None
    summary_text: Optional[str] = None
    amount: Optional[str] = None
    deadline: Optional[str] = None
    keywords: list[str] = []
    published_at: Optional[str] = None
    summarized_at: Optional[str] = None


class FacetItem(BaseModel):
    """单条筛选项(供 sidebar 渲染 checkbox + count)。"""
    value: str
    count: int


class PoliciesSearchOut(BaseModel):
    policies: list[PolicyWithSourceOut] = []
    facets: dict[str, list[FacetItem]] = {}
    total: int = 0


@router.get("/policies/search", response_model=PoliciesSearchOut)
async def search_policies(
    region: list[str] = Query(default_factory=list, description="国家级/省级/市级/区级(多选)"),
    department: list[str] = Query(default_factory=list, description="委办部门(多选)"),
    category: list[str] = Query(default_factory=list, description="类目(多选)"),
    source_id: list[str] = Query(default_factory=list, description="具体源 ID(多选)"),
    query: str = Query(default="", description="标题关键词搜索"),
    limit: int = Query(default=100, ge=1, le=500),
    summarized_only: bool = Query(default=False),
) -> PoliciesSearchOut:
    """多维筛选政策 + facets。

    用法(前端 sidebar):
    - region/department/category/source_id 都是数组,可多选
    - facets 返回每个维度可选项 + count,直接渲染 checkbox + 数量

    count 语义:每个 facet value 在当前 query 结果下命中的 policy 数。
    """
    async with get_session() as session:
        # 1) 拉所有 PolicySource
        src_rows = (await session.execute(select(PolicySource))).scalars().all()
        src_by_id = {s.id: s for s in src_rows}

        # 2) source-level filter:从 src_rows 中过滤候选
        if region or department or category or source_id:
            candidate_pkids = [
                s.id for s in src_rows
                if (not region or (s.region in region))
                and (not department or (s.department in department))
                and (not category or (s.category in category))
                and (not source_id or (s.source_id in source_id))
            ]
        else:
            candidate_pkids = list(src_by_id.keys())

        if not candidate_pkids:
            return PoliciesSearchOut(policies=[], facets={}, total=0)

        # 3) 查 Policy
        stmt = select(Policy).where(Policy.source_id.in_(candidate_pkids))
        if query:
            stmt = stmt.where(Policy.title.contains(query))
        if summarized_only:
            stmt = stmt.where(Policy.summary_text.isnot(None))
        stmt = stmt.order_by(desc(Policy.id)).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()

        # 4) 拼装 policy(带 source 元数据)
        out_policies = []
        for p in rows:
            s = src_by_id.get(p.source_id)
            out_policies.append(
                PolicyWithSourceOut(
                    id=p.id,
                    title=p.title,
                    url=p.url,
                    source_id=s.source_id if s else "?",
                    region=s.region if s else None,
                    department=s.department if s else None,
                    category=s.category if s else None,
                    summary_type=p.summary_type,
                    summary_text=p.summary_text,
                    amount=(p.summary_data or {}).get("amount") if p.summary_data else None,
                    deadline=(p.summary_data or {}).get("deadline") if p.summary_data else None,
                    keywords=(p.summary_data or {}).get("keywords", []) if p.summary_data else [],
                    published_at=p.published_at.isoformat() if p.published_at else None,
                    summarized_at=p.summarized_at.isoformat() if p.summarized_at else None,
                )
            )

        # 5) facets:当前结果下,每维度可选项 + count(命中 policy 数)
        region_pol = Counter()
        dept_pol = Counter()
        cat_pol = Counter()
        for p in rows:
            s = src_by_id.get(p.source_id)
            if not s:
                continue
            if s.region:
                region_pol[s.region] += 1
            if s.department:
                dept_pol[s.department] += 1
            if s.category:
                cat_pol[s.category] += 1

        # 全 dim 可选值(从 src_rows 去重;有序按 count 倒序)
        regions_all = sorted({s.region for s in src_rows if s.region},
                             key=lambda v: -region_pol.get(v, 0))
        depts_all = sorted({s.department for s in src_rows if s.department},
                           key=lambda v: -dept_pol.get(v, 0))
        cats_all = sorted({s.category for s in src_rows if s.category},
                          key=lambda v: -cat_pol.get(v, 0))

        facets = {
            "regions": [FacetItem(value=v, count=region_pol.get(v, 0)) for v in regions_all],
            "departments": [FacetItem(value=v, count=dept_pol.get(v, 0)) for v in depts_all],
            "categories": [FacetItem(value=v, count=cat_pol.get(v, 0)) for v in cats_all],
        }

        return PoliciesSearchOut(policies=out_policies, facets=facets, total=len(out_policies))
