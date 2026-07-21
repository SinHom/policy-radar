"""一次性回填：从 spider_config JSON 提取 region/department 到 PolicySource 表列。

临时脚本：因为 seed_sources.py 没把 region/department 提取到列，只塞进 spider_config JSON。
advisor_fushun 检索 region.like('%抚顺%') 查的是列不是 JSON，所以必须回填。
"""
from __future__ import annotations
import asyncio
import json
import logging
import sys
from sqlalchemy import select, update

from python.models import PolicySource
from python.models.base import init_session_factory, make_engine, get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_region")


async def main():
    engine = make_engine()
    init_session_factory(engine)
    updated = 0
    skipped = 0
    async with get_session() as session:
        rows = (await session.execute(
            select(PolicySource.source_id, PolicySource.spider_config, PolicySource.region, PolicySource.department)
        )).all()
        for sid, cfg, cur_region, cur_dept in rows:
            if not cfg:
                continue
            new_region = cfg.get("region")
            new_dept = cfg.get("department")
            if not new_region and not new_dept:
                continue
            # 仅当列当前为空 或 与 spider_config 不一致时回填
            if (cur_region == new_region and cur_dept == new_dept):
                skipped += 1
                continue
            await session.execute(
                update(PolicySource)
                .where(PolicySource.source_id == sid)
                .values(region=new_region, department=new_dept)
            )
            logger.info("Updated %s: region=%r, department=%r", sid, new_region, new_dept)
            updated += 1
        await session.commit()
    logger.info("Updated %d, skipped %d", updated, skipped)


if __name__ == "__main__":
    asyncio.run(main())