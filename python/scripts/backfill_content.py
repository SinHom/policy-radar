"""批量回填空正文：用 Playwright 重抓所有 empty raw_content 的政策 URL。

用法：
    python -m scripts.backfill_content          # 回填所有空正文
    python -m scripts.backfill_content --limit 10 --dry-run  # 预览前 10 条
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select, update

from python.models import Policy
from python.models.base import get_session, init_session_factory, make_engine
from python.crawlers.fetcher import Fetcher, FetchResult
from python.crawlers.parser import extract_by_selector, parse_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")

# 广泛的内容选择器（按优先级尝试）
CONTENT_SELECTORS = [
    ".TRS_Editor",
    "#UCAP-CONTENT",
    ".article-content",
    ".article_content",
    ".content",
    ".zw_content",
    ".TRS_PreAppend",
    ".Custom_UnionStyle",
    ".xxgk_content",
    ".detail-content",
    ".detail_content",
    ".news-content",
    ".info-content",
    "article",
    ".main-content",
    "#content",
    ".text-content",
    ".con",
    ".bt_content",
    ".wz_content",
    ".nr",
    ".main",
]

# 最小正文长度（字符），低于此值视为无内容
MIN_CONTENT_LENGTH = 200

# 并发数
CONCURRENCY = 3


async def backfill_one(
    fetcher: Fetcher,
    policy_id: int,
    url: str,
    dry_run: bool = False,
) -> tuple[int, bool, str]:
    """回填单条政策。返回 (policy_id, success, reason)。"""
    try:
        # 用 Playwright 抓（确保 JS 渲染）
        result: FetchResult = await fetcher.fetch(url, render_js=True)
    except Exception as e:
        return (policy_id, False, f"fetch_failed:{e}")

    if not result.html or len(result.html) < MIN_CONTENT_LENGTH:
        return (policy_id, False, f"html_too_short:{len(result.html)}")

    soup = parse_html(result.html)

    # 按优先级尝试内容选择器
    content = None
    matched_sel = None
    for sel in CONTENT_SELECTORS:
        try:
            extracted = extract_by_selector(soup, sel)
            if extracted and len(extracted.strip()) > MIN_CONTENT_LENGTH:
                content = extracted
                matched_sel = sel
                break
        except Exception:
            continue

    # fallback: 用 body 文本（去 script/style）
    if not content:
        try:
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            body_text = soup.get_text("\n", strip=True)
            if len(body_text) > 200:
                content = body_text
                matched_sel = "body(fallback)"
        except Exception:
            pass

    if not content:
        return (policy_id, False, "no_content_matched")

    if dry_run:
        return (policy_id, True, f"DRY_RUN:{matched_sel}:{len(content)}chars")

    # 更新 DB
    try:
        async with get_session() as session:
            stmt = (
                update(Policy)
                .where(Policy.id == policy_id)
                .values(
                    raw_content=content[:200000],
                    full_text_fetched_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()
    except Exception as e:
        return (policy_id, False, f"db_update_failed:{e}")

    return (policy_id, True, f"{matched_sel}:{len(content)}chars")


async def backfill(
    *,
    limit: int = 0,
    dry_run: bool = False,
    concurrency: int = CONCURRENCY,
) -> dict:
    """回填所有空正文政策。"""
    engine = make_engine()
    init_session_factory(engine)

    # 查询所有空正文的政策
    async with get_session() as session:
        stmt = (
            select(Policy)
            .where(
                (Policy.raw_content.is_(None)) | (Policy.raw_content == "")
            )
            .where(Policy.url.notlike("mock://%"))
            .order_by(Policy.id)
        )
        if limit > 0:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    total = len(rows)
    logger.info("待回填: %d 条 (limit=%d, dry_run=%s)", total, limit, dry_run)

    fetcher = Fetcher(request_interval_min=1.0, request_interval_max=3.0, timeout=45.0)

    success = 0
    failed = 0
    skipped_noise = 0
    sem = asyncio.Semaphore(concurrency)

    async def worker(pol: Policy) -> tuple[int, bool, str]:
        async with sem:
            return await backfill_one(fetcher, pol.id, pol.url, dry_run=dry_run)

    tasks = [worker(p) for p in rows]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, Exception):
            failed += 1
            logger.error("worker_exception: %s", r)
            continue
        pid, ok, reason = r
        if ok:
            success += 1
            logger.info("[OK] #%d: %s", pid, reason)
        elif "skip_noise" in reason:
            skipped_noise += 1
            logger.debug("[SKIP] #%d: %s", pid, reason)
        else:
            failed += 1
            logger.warning("[FAIL] #%d: %s | %s", pid, reason[:50],
                          f"url={rows[0].url[:80]}" if rows else "")

    stats = {
        "total": total,
        "success": success,
        "failed": failed,
        "skipped_noise": skipped_noise,
    }
    logger.info("回填完成: %s", stats)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="批量回填政策正文")
    parser.add_argument("--limit", type=int, default=0, help="限制条数（0=不限制）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写DB")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY, help="并发数")
    args = parser.parse_args()

    stats = asyncio.run(backfill(
        limit=args.limit,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
    ))

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}回填统计: {stats}")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
