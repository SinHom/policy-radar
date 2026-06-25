"""端到端联调脚本。

流程：
    1. seed_sources → 3 个政策源
    2. seed_policies → 5 条 mock 政策
    3. summarize_pending → LLM 摘要
    4. push first policy → Mock 微信

运行：
    python -m scripts.e2e

要求：mock_wechat 服务在 9999 端口运行（python -m mock）。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime

import httpx

from python.ai.summarizer import summarize_pending
from python.app.api.routes import format_push_message
from python.app.config import get_settings
from python.models import Policy
from python.models.base import get_session, init_session_factory, make_engine
from python.scripts import seed_policies, seed_sources
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e")


async def step_1_seed_sources() -> int:
    """seed_sources.seed() 是 async 函数。"""
    logger.info("=== Step 1/4: seed sources ===")
    return await seed_sources.seed()


async def step_2_seed_policies() -> int:
    logger.info("=== Step 2/4: seed policies ===")
    return await seed_policies.seed()


async def step_3_summarize(limit: int = 5) -> list[dict]:
    logger.info("=== Step 3/4: summarize ===")
    return await summarize_pending(limit=limit)


async def step_4_push_one(policy_id: int) -> bool:
    logger.info(f"=== Step 4/4: push policy #{policy_id} ===")
    settings = get_settings()

    async with get_session() as session:
        stmt = select(Policy).where(Policy.id == policy_id)
        pol = (await session.execute(stmt)).scalar_one_or_none()
        if pol is None:
            logger.error(f"Policy #{policy_id} not found")
            return False
        if not pol.summary_text:
            logger.error(f"Policy #{policy_id} not summarized")
            return False
        content = format_push_message(pol)

    target = "e2e-test-ctx"
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
        logger.info(f"Push OK ({len(content)} chars) -> {target}")
        return True
    except Exception as e:
        logger.exception(f"Push failed: {e}")
        return False


async def main_async() -> int:
    settings = get_settings()
    engine = make_engine()
    init_session_factory(engine)

    t0 = datetime.now()

    # 1: seed_sources 是 async 函数
    n_src = await step_1_seed_sources()
    logger.info(f"  -> {n_src} sources ready")

    # 2
    n_pol = await step_2_seed_policies()
    logger.info(f"  -> {n_pol} policies ready")

    # 3
    results = await step_3_summarize(limit=5)
    ok = sum(1 for r in results if r.get("ok"))
    logger.info(f"  -> {ok}/{len(results)} summarized")

    # 4: 推送第一条已摘要的
    pushed = False
    async with get_session() as session:
        stmt = select(Policy).where(Policy.summary_text.isnot(None)).order_by(Policy.id).limit(1)
        pol = (await session.execute(stmt)).scalar_one_or_none()
        if pol:
            pushed = await step_4_push_one(pol.id)
    logger.info(f"  -> push OK: {pushed}")

    elapsed = (datetime.now() - t0).total_seconds()
    print()
    print("=" * 50)
    passed = pushed and ok == 5
    print(f"e2e {'PASS' if passed else 'FAIL'}")
    print(f"  sources:    {n_src}")
    print(f"  policies:   {n_pol}")
    print(f"  summarized: {ok}/5")
    print(f"  push:       {'OK' if pushed else 'FAIL'}")
    print(f"  elapsed:    {elapsed:.1f}s")
    print("=" * 50)
    return 0 if passed else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
