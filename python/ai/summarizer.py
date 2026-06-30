"""政策摘要：取 DB 中未摘要的政策，调 LLM 生成结构化 JSON 摘要，写回 DB。"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from python.ai.llm_client import LLMClient, get_llm_client
from python.models import Policy
from python.models.base import get_session, init_session_factory, make_engine

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent / "prompts" / "summary.txt"
MAX_CHARS = int(os.environ.get("LLM_TEXT_MAX_CHARS", "6000"))
CONCURRENCY = int(os.environ.get("LLM_SUMMARIZE_CONCURRENCY", "2"))


def _load_prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    """超长文本截断到 max_chars 字。"""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n...(以下内容已截断)"


async def summarize_one(
    policy_id: int,
    *,
    llm: Optional[LLMClient] = None,
) -> dict:
    """摘要单条政策。返回写入的 summary_data。"""
    llm = llm or await get_llm_client()

    async with get_session() as session:
        stmt = select(Policy).where(Policy.id == policy_id)
        pol = (await session.execute(stmt)).scalar_one_or_none()
        if pol is None:
            raise ValueError(f"Policy {policy_id} not found")
        if pol.summary_text:
            logger.info("Policy %d already summarized, skip", policy_id)
            return pol.summary_data or {}
        text = pol.raw_content or pol.title
        title = pol.title

    truncated = _truncate(text)
    template = _load_prompt_template()
    user_prompt = template.format(policy_text=truncated)
    system_prompt = "你是政策分析专家，输出严格的 JSON 格式。"

    logger.info("Summarizing policy %d (chars=%d)", policy_id, len(truncated))
    data = await llm.chat_json(system=system_prompt, user=user_prompt)

    # 兼容不同模型的字段差异，做一些归一化
    title_simple = data.get("title") or data.get("title_simple") or title
    ptype = data.get("type") or "其他"
    summary = data.get("summary") or data.get("summary_text") or ""
    target = data.get("target_enterprise") or ""
    amount = data.get("amount")
    deadline_str = data.get("deadline")
    conditions = data.get("conditions") or []
    keywords = data.get("keywords") or []
    advisory = data.get("advisory") or ""  # 业务解读 200字内

    # 解析 deadline 为 date（容错）
    parsed_deadline = None
    if deadline_str and deadline_str != "null":
        from datetime import date
        try:
            parsed_deadline = date.fromisoformat(str(deadline_str))
        except (ValueError, TypeError):
            parsed_deadline = None

    async with get_session() as session:
        stmt = select(Policy).where(Policy.id == policy_id)
        pol = (await session.execute(stmt)).scalar_one_or_none()
        if pol is None:
            raise ValueError(f"Policy {policy_id} disappeared")
        pol.summary_type = ptype
        pol.summary_text = summary
        pol.summary_data = data
        pol.summary_model = llm.model
        pol.summarized_at = datetime.utcnow()
        # 摘要 200-300 字最多 500;advisory 同样限制
        pol.advisory = (advisory or "")[:600]
        # 顺便：把简化标题写回 title 字段（如果新标题更短）
        if title_simple and len(title_simple) < len(pol.title):
            pass  # 不覆盖原 title，避免丢失信息
    return data


async def summarize_pending(
    *,
    limit: int = 10,
    llm: Optional[LLMClient] = None,
) -> list[dict]:
    """批量摘要：取所有未摘要的政策，限流并发。"""
    llm = llm or await get_llm_client()

    async with get_session() as session:
        stmt = (
            select(Policy.id)
            .where(Policy.summary_text.is_(None))
            .where(Policy.raw_content.isnot(None))
            .order_by(Policy.id)
            .limit(limit)
        )
        ids = list((await session.execute(stmt)).scalars().all())

    if not ids:
        logger.info("No pending policies to summarize")
        return []

    sem = asyncio.Semaphore(CONCURRENCY)
    results: list[dict] = []

    async def _run(pid: int):
        async with sem:
            try:
                data = await summarize_one(pid, llm=llm)
                results.append({"policy_id": pid, "ok": True, "data": data})
            except Exception as e:
                logger.exception("Summarize policy %d failed: %s", pid, e)
                results.append({"policy_id": pid, "ok": False, "error": str(e)})

    await asyncio.gather(*[_run(pid) for pid in ids])
    return results
