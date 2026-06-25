"""爬虫 CLI 入口。

用法：
    python -m crawlers --source sz_gxj
    python -m crawlers --source sz_gxj --source gd_kjt
    python -m crawlers --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from python.crawlers.engine import run_crawler

# 让 python 路径生效
sys.path.insert(0, ".")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Policy Radar Crawler")
    p.add_argument("--source", "-s", action="append", help="policy source_id (可多次传)")
    p.add_argument("--all", action="store_true", help="爬取所有 enabled 源")
    p.add_argument("--max-new", type=int, default=20, help="每源最多新增 N 条（默认 20）")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


async def main_async() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.source and not args.all:
        print("ERROR: 请传 --source <id> 或 --all", file=sys.stderr)
        return 1

    source_ids = args.source if args.source else None
    results = await run_crawler(source_ids=source_ids, max_new_per_source=args.max_new)

    # 打印汇总
    print("\n========== 爬取汇总 ==========")
    print(json.dumps(
        [
            {
                "source_id": r.source_id,
                "total_listed": r.total_listed,
                "new_crawled": r.new_crawled,
                "skipped_duplicate": r.skipped_duplicate,
                "errors": r.errors,
                "error_messages": r.error_messages[:3],
            }
            for r in results
        ],
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
