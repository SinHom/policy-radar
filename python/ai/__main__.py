"""LLM 摘要 CLI 入口。

用法：
    python -m ai --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from python.ai.llm_client import get_llm_client
from python.ai.summarizer import summarize_pending
from python.models.base import init_session_factory, make_engine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Policy Radar AI Summarizer")
    p.add_argument("--limit", "-n", type=int, default=5, help="最多摘要 N 条（默认 5）")
    p.add_argument("--health-check", action="store_true", help="只验证 API 可用性")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


async def main_async() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 初始化 DB session
    engine = make_engine()
    init_session_factory(engine)

    # 健康检查
    if args.health_check:
        llm = get_llm_client()
        ok = await llm.health_check()
        print("LLM health check:", "OK" if ok else "FAILED")
        return 0 if ok else 1

    # 摘要
    results = await summarize_pending(limit=args.limit)
    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"\n=== 摘要完成 ===  成功 {ok_count}/{len(results)}")
    for r in results:
        if r.get("ok"):
            data = r.get("data") or {}
            print(f"  [{r['policy_id']}] type={data.get('type','?')} | {data.get('summary','')[:60]}")
        else:
            print(f"  [{r['policy_id']}] FAILED: {r.get('error','')[:100]}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
