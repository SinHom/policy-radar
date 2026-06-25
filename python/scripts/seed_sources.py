"""预置 3 个政策源到 DB。

读 python/crawlers/spiders/*.json，把 source_id/name/url/category/spider_config
写入 policy_sources 表（已存在则更新 spider_config 和 enabled 状态）。

用法：
    python -m scripts.seed_sources
"""

from __future__ import annotations

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


SEED_SOURCES = [
    {"source_id": "sz_gxj", "name": "深圳市工信局", "category": "市级"},
    {"source_id": "gd_kjt", "name": "广东省科技厅", "category": "省级"},
    {"source_id": "gov_cn", "name": "国务院", "category": "国家级"},
]


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

    for meta in SEED_SOURCES:
        sid = meta["source_id"]
        cfg_path = SPIDERS_DIR / f"{sid}.json"
        if not cfg_path.exists():
            logger.warning("Spider config not found, skip: %s", cfg_path)
            continue
        with cfg_path.open("r", encoding="utf-8") as f:
            spider_config = json.load(f)
        url = spider_config.get("list_url", "")

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
                    enabled=True,
                ))
                logger.info("Inserted: %s", sid)
            count += 1

    logger.info("Seeded %d sources", count)
    return count


def main() -> int:
    return asyncio.run(seed())


if __name__ == "__main__":
    sys.exit(main())
