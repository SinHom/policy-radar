"""管理类 Tools：trigger_crawl。"""

from __future__ import annotations

import json
import logging

from python.crawlers.engine import crawl_source, run_crawler

logger = logging.getLogger(__name__)


async def handle_trigger_crawl(arguments: dict) -> list[dict]:
    """trigger_crawl 实现。"""
    source_id = arguments.get("source_id")
    try:
        if source_id:
            r = await crawl_source(source_id)
            results = [{
                "source_id": r.source_id,
                "total_listed": r.total_listed,
                "new_crawled": r.new_crawled,
                "skipped_duplicate": r.skipped_duplicate,
                "errors": r.errors,
                "error_messages": r.error_messages[:3],
            }]
        else:
            results = await run_crawler()
            results = [
                {
                    "source_id": r.source_id,
                    "total_listed": r.total_listed,
                    "new_crawled": r.new_crawled,
                    "skipped_duplicate": r.skipped_duplicate,
                    "errors": r.errors,
                    "error_messages": r.error_messages[:3],
                }
                for r in results
            ]
        total_new = sum(r.get("new_crawled", 0) for r in results)
        return [{
            "type": "text",
            "text": json.dumps({
                "status": "ok",
                "total_new": total_new,
                "results": results,
            }, ensure_ascii=False),
        }]
    except Exception as e:
        logger.exception("trigger_crawl failed: %s", e)
        return [{
            "type": "text",
            "text": json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False),
        }]
