"""URL 去重：与 DB 已有 policies.url 集合比对。"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from python.models import Policy


async def get_existing_urls(
    session: AsyncSession, urls: Iterable[str]
) -> set[str]:
    """查询 DB 中已存在的 URL 集合。"""
    url_list = list(set(urls))  # 去重
    if not url_list:
        return set()
    stmt = select(Policy.url).where(Policy.url.in_(url_list))
    result = await session.execute(stmt)
    return {row[0] for row in result.all()}


async def is_duplicate(session: AsyncSession, url: str) -> bool:
    """单条 URL 是否已存在。"""
    stmt = select(Policy.id).where(Policy.url == url).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
