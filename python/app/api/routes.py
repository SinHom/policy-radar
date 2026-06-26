"""业务 API 路由（MVP：4 个核心端点 + 推送日志）。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
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
async def list_sources():
    """列出所有政策源。"""
    async with get_session() as session:
        stmt = select(PolicySource).order_by(PolicySource.id)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": s.id,
                "source_id": s.source_id,
                "name": s.name,
                "category": s.category,
                "enabled": s.enabled,
                "last_crawl_at": s.last_crawl_at.isoformat() if s.last_crawl_at else None,
                "last_status": s.last_status,
            }
            for s in rows
        ]


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
