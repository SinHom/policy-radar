"""预置所有政策源到 DB（自动扫描 spiders/ 目录）。

读 python/crawlers/spiders/*.json，把 source_id/name/url/category/spider_config
写入 policy_sources 表（已存在则更新 spider_config 和 enabled 状态）。

自动发现 12+ 源：4 国家级 + 3 省级 + 5 市级。

用法：
    python -m scripts.seed_sources
    python -m scripts.seed_sources --disable city_bj_gxj  # 禁用一个
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from python.crawlers.engine import SPIDERS_DIR
from python.models import PolicySource
from python.models.base import init_session_factory, make_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_sources")


def discover_sources() -> list[dict]:
    """扫描 spiders/ 目录，返回所有 source metadata。"""
    sources = []
    for cfg_path in sorted(SPIDERS_DIR.glob("*.json")):
        try:
            with cfg_path.open(encoding="utf-8") as f:
                cfg = json.load(f)
            sources.append({
                "source_id": cfg["source_id"],
                "name": cfg["name"],
                "category": cfg.get("category", ""),
                "url": cfg.get("list_url", ""),
                "spider_config": cfg,
            })
        except Exception as e:
            logger.warning("skip %s: %s", cfg_path.name, e)
    return sources


async def seed() -> int:
    engine = make_engine()
    init_session_factory(engine)

    count = 0
    async with engine.begin() as conn:
        # SQLAlchemy 2.0 async with engine.begin() 拿的是 AsyncConnection
        from python.models.base import AsyncSessionLocal
        pass

    # 改为用 session
    from python.models.base import get_session

    sources = discover_sources()
    logger.info("Discovered %d spider configs", len(sources))

    for meta in sources:
        sid = meta["source_id"]
        spider_config = meta["spider_config"]
        url = meta["url"]
        disable = getattr(seed, "_disable_ids", set())
        enabled = sid not in disable

        async with get_session() as session:
            stmt = select(PolicySource).where(PolicySource.source_id == sid)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                existing.name = meta["name"]
                existing.category = meta["category"]
                existing.url = url
                existing.spider_config = spider_config
                logger.info("Updated: %s", sid)
            else:
                session.add(PolicySource(
                    source_id=sid,
                    name=meta["name"],
                    url=url,
                    category=meta["category"],
                    spider_config=spider_config,
                    frequency=spider_config.get("frequency", "daily"),
                    enabled=enabled,
                ))
                logger.info("Inserted: %s (enabled=%s)", sid, enabled)
            count += 1

    logger.info("Seeded %d sources", count)
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disable", nargs="*", default=[], help="source_ids to disable")
    args = parser.parse_args()
    seed._disable_ids = set(args.disable)
    return asyncio.run(seed())


if __name__ == "__main__":
    sys.exit(main())
