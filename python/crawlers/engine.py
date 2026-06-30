"""爬虫引擎：读 JSON 配置 → 抓列表 → 抓详情 → 入库。

每个政策源 = 一份 JSON 配置（spiders/*.json），不写代码。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from python.crawlers.dedup import is_duplicate
from python.crawlers.fetcher import Fetcher, get_fetcher
from python.crawlers.parser import (
    extract_all,
    extract_by_selector,
    extract_date,
    parse_html,
)
from python.models import Policy, PolicySource, get_session
from python.models.base import init_session_factory, make_engine

logger = logging.getLogger(__name__)

SPIDERS_DIR = Path(__file__).resolve().parent / "spiders"


@dataclass
class CrawlResult:
    """一次爬取的统计。"""

    source_id: str
    total_listed: int = 0
    new_crawled: int = 0
    skipped_duplicate: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)


def load_spider_config(source_id: str) -> dict:
    """按 source_id 加载 JSON 配置。"""
    path = SPIDERS_DIR / f"{source_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Spider config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def crawl_source(
    source_id: str,
    *,
    fetcher: Optional[Fetcher] = None,
    max_new: int = 50,
) -> CrawlResult:
    """爬取单个政策源。支持 html(默认) 和 rss 两种模式(看 spider.json.mode)。"""
    cfg = load_spider_config(source_id)
    fetcher = fetcher or get_fetcher()
    result = CrawlResult(source_id=source_id)

    if cfg.get("mode") == "rss":
        # RSS 模式: 走 rss_crawler(feed → parse → 入库,无 detail 二次抓取)
        from python.crawlers.rss_crawler import rss_crawl_source
        return await rss_crawl_source(
            source_id, cfg, fetcher=fetcher, max_new=max_new
        )

    # 1. 抓列表页
    list_url = cfg["list_url"]
    list_selectors = cfg.get("list_selectors", {})
    render_js = cfg.get("render_js", False)

    logger.info("[%s] Fetching list: %s", source_id, list_url)
    try:
        list_page = await fetcher.fetch(list_url, render_js=render_js)
        from python.crawlers.alerts import record_success
        record_success(source_id)
    except Exception as e:
        msg = f"List page fetch failed: {e}"
        logger.exception(msg)
        result.errors += 1
        result.error_messages.append(msg)
        from python.crawlers.alerts import record_failure
        record_failure(source_id, str(e))
        return result

    soup = parse_html(list_page.html)
    item_sel = list_selectors.get("item")
    if not item_sel:
        msg = f"list_selectors.item missing in config"
        result.errors += 1
        result.error_messages.append(msg)
        return result

    items = extract_all(soup, item_sel)
    result.total_listed = len(items)
    logger.info("[%s] Found %d items in list", source_id, len(items))

    # 2. 抽每条 item 的 title/href/date
    title_sel = list_selectors.get("title", "a::text")
    href_sel = list_selectors.get("href", "a::attr(href)")
    date_sel = list_selectors.get("date", "")

    candidates: list[dict] = []
    for el in items:
        # 处理 title/href 可能是选择器（如 a::text, a::attr(href)）
        # 简化为：先按 href_sel 抽链接，title 用 el 的纯文本或子元素
        if href_sel.startswith("a::attr") or href_sel == "a::attr(href)":
            href = el.get("href", "") if el.name == "a" else extract_by_selector(parse_html(str(el)), href_sel)
        else:
            href = extract_by_selector(parse_html(str(el)), href_sel, attr="href")
        if not href:
            continue
        # 拼完整 URL
        full_url = urljoin(list_page.final_url, href)
        # title：list_selectors.title 可以是 CSS 或者 ::text
        # 简化：从 el 本身抽文本
        title = el.get_text(strip=True) if el.name != "a" else el.get_text(strip=True)
        if not title and title_sel:
            title = extract_by_selector(parse_html(str(el)), title_sel)
        date_text = ""
        if date_sel:
            try:
                date_text = extract_by_selector(parse_html(str(el)), date_sel)
            except Exception:
                pass
        candidates.append({"url": full_url, "title": title, "date_text": date_text})

    # 3. 找 DB 里 source_id 对应的 source
    async with get_session() as session:
        from sqlalchemy import select
        stmt = select(PolicySource).where(PolicySource.source_id == source_id)
        source_obj = (await session.execute(stmt)).scalar_one_or_none()
        if source_obj is None:
            msg = f"PolicySource {source_id} not found in DB; run seed_sources first"
            result.errors += 1
            result.error_messages.append(msg)
            return result
        db_source_id = source_obj.id

    # 4. 去重 + 抓详情 + 入库
    detail_selectors = cfg.get("detail_selectors", {})
    for cand in candidates[: max_new * 2]:  # 多取一些以弥补去重
        if result.new_crawled >= max_new:
            break
        url = cand["url"]
        try:
            async with get_session() as session:
                if await is_duplicate(session, url):
                    result.skipped_duplicate += 1
                    continue

            # 抓详情
            logger.info("[%s] Fetching detail: %s", source_id, url)
            detail = await fetcher.fetch(url, render_js=render_js)
            detail_soup = parse_html(detail.html)

            # 抽 title / content / date
            detail_title = (
                extract_by_selector(detail_soup, detail_selectors.get("title", "h1"))
                or cand["title"]
            )
            detail_content = extract_by_selector(
                detail_soup, detail_selectors.get("content", "body")
            )
            detail_date_text = (
                extract_by_selector(detail_soup, detail_selectors.get("date", ""))
                or cand.get("date_text", "")
            )
            pub_date = extract_date(detail_date_text)

            # 入库(必须 commit,否则 session 关闭时丢弃)
            async with get_session() as session:
                pol = Policy(
                    source_id=db_source_id,
                    url=url,
                    title=detail_title[:512] or cand["title"][:512] or "(无标题)",
                    raw_content=detail_content[:100000] if detail_content else None,
                    published_at=pub_date,
                    crawled_at=datetime.utcnow(),
                )
                session.add(pol)
                await session.commit()
            result.new_crawled += 1
            logger.info(
                "[%s] New policy: %s | %s",
                source_id,
                url[:80],
                (detail_title or cand["title"])[:50],
            )
        except Exception as e:
            msg = f"Detail failed for {url}: {e}"
            logger.exception(msg)
            result.errors += 1
            result.error_messages.append(msg)

    # 5. 更新 source.last_crawl_at / last_status(必须 commit)
    async with get_session() as session:
        from sqlalchemy import select
        stmt = select(PolicySource).where(PolicySource.source_id == source_id)
        source_obj = (await session.execute(stmt)).scalar_one_or_none()
        if source_obj:
            source_obj.last_crawl_at = datetime.utcnow()
            source_obj.last_status = "ok" if result.errors == 0 else "failed"
            await session.commit()

    return result


async def run_crawler(
    source_ids: Optional[list[str]] = None,
    *,
    max_new_per_source: int = 10,
) -> list[CrawlResult]:
    """跑多个爬虫源。source_ids 为 None 时跑所有 enabled 源。"""
    # 初始化 session
    engine = make_engine()
    init_session_factory(engine)

    if source_ids is None:
        async with get_session() as session:
            from sqlalchemy import select
            stmt = select(PolicySource.source_id).where(PolicySource.enabled.is_(True))
            rows = (await session.execute(stmt)).scalars().all()
            source_ids = list(rows)
    if not source_ids:
        logger.warning("No enabled sources to crawl")
        return []

    logger.info("Crawling %d sources: %s", len(source_ids), source_ids)
    results = []
    for sid in source_ids:
        try:
            r = await crawl_source(sid, max_new=max_new_per_source)
            results.append(r)
            logger.info(
                "[%s] Done: +%d new, %d skipped, %d errors",
                sid, r.new_crawled, r.skipped_duplicate, r.errors,
            )
        except Exception as e:
            logger.exception("[%s] Crawl failed: %s", sid, e)
            results.append(CrawlResult(source_id=sid, errors=1, error_messages=[str(e)]))
    return results
