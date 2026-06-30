"""RSS 模式爬虫:RSS feed 直接抓取 + 入库(不走 HTML+selectors)。

设计:与 HTML 模式(crawl_source)平行,各自走完整 fetch → parse → dedup → insert。
RSS 模式下每个 <item> 含 title/link/pubDate/description,不需 detail 二次抓取。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from python.crawlers.dedup import is_duplicate
from python.crawlers.engine import CrawlResult, get_session
from python.crawlers.fetcher import Fetcher, get_fetcher
from python.crawlers.parser import extract_date
from python.crawlers.rss_parser import clean_description, parse_rss
from python.models import Policy, PolicySource

logger = logging.getLogger(__name__)


async def rss_crawl_source(
    source_id: str,
    cfg: dict,
    *,
    fetcher: Optional[Fetcher] = None,
    max_new: int = 10,
) -> CrawlResult:
    """RSS 模式单源抓取+入库。

    cfg: spider json dict(list_url + 可选 render_js)
    返回 CrawlResult(total_listed/new_crawled/skipped_duplicate/errors/error_messages)
    """
    fetcher = fetcher or get_fetcher()
    result = CrawlResult(source_id=source_id)

    list_url = cfg.get("list_url")
    if not list_url:
        msg = "spider.json 缺 list_url"
        result.errors += 1
        result.error_messages.append(msg)
        return result

    render_js = cfg.get("render_js", False)

    # 1) 抓 RSS XML(可能要走 Playwright — 政府站偶尔有反爬)
    try:
        page = await fetcher.fetch(list_url, render_js=render_js)
    except Exception as e:
        msg = f"RSS fetch failed: {e}"
        logger.exception(msg)
        result.errors += 1
        result.error_messages.append(msg)
        return result

    # 2) 解析
    try:
        items = parse_rss(page.html)
    except Exception as e:
        msg = f"RSS parse failed: {e}"
        logger.exception(msg)
        result.errors += 1
        result.error_messages.append(msg)
        return result
    result.total_listed = len(items)
    logger.info("[%s] RSS items: %d", source_id, len(items))

    # 3) 找 DB source
    async with get_session() as session:
        stmt = select(PolicySource).where(PolicySource.source_id == source_id)
        source_obj = (await session.execute(stmt)).scalar_one_or_none()
        if source_obj is None:
            msg = f"PolicySource {source_id} not found in DB; run seed_sources first"
            result.errors += 1
            result.error_messages.append(msg)
            return result
        db_source_id = source_obj.id

    # 4) 去重 + 入库(RSS 不需二次 detail 抓取,item 已含 title/description)
    for item in items[: max_new * 2]:
        if result.new_crawled >= max_new:
            break
        link = (item.link or "").strip()
        if not link:
            continue
        try:
            async with get_session() as session:
                if await is_duplicate(session, link):
                    result.skipped_duplicate += 1
                    continue

            pub_date = extract_date(item.pub_date) if item.pub_date else None
            desc_clean = clean_description(item.description) if item.description else None

            async with get_session() as session:
                pol = Policy(
                    source_id=db_source_id,
                    url=link,
                    title=(item.title or "(无标题)")[:512],
                    raw_content=desc_clean[:100000] if desc_clean else None,
                    published_at=pub_date,
                    crawled_at=datetime.utcnow(),
                )
                session.add(pol)
                await session.commit()
            result.new_crawled += 1
            logger.info(
                "[%s] RSS new: %s | %s",
                source_id,
                link[:80],
                (item.title or "")[:50],
            )
        except Exception as e:
            msg = f"RSS insert failed for {link}: {e}"
            logger.exception(msg)
            result.errors += 1
            result.error_messages.append(msg)

    # 5) 更新 source.last_crawl_at(必须 commit)
    async with get_session() as session:
        stmt = select(PolicySource).where(PolicySource.source_id == source_id)
        source_obj = (await session.execute(stmt)).scalar_one_or_none()
        if source_obj:
            source_obj.last_crawl_at = datetime.utcnow()
            # last_status 不强求,后端如有 alerts 模块会用
            await session.commit()

    return result
