"""内存高效回填：单 Playwright 浏览器复用，逐条处理，分批重启。

与 backfill_content.py 的区别：
- 复用浏览器实例（不每条 URL 起新 Chromium）
- 单并发（避免 2C4G OOM）
- 每 50 条重启浏览器（释放内存）
- 先 httpx 快试，403 才切 Playwright

用法：
    python -m scripts.backfill_batch              # 处理全部
    python -m scripts.backfill_batch --limit 50   # 只处理 50 条
"""

import asyncio, sys, logging, argparse
sys.path.insert(0, '/app')

from sqlalchemy import select, update
from python.models import Policy
from python.models.base import get_session, init_session_factory, make_engine
from python.crawlers.parser import parse_html, extract_by_selector
from datetime import datetime, timezone
import httpx
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bf_batch")

CONTENT_SELECTORS = [
    '.TRS_Editor', '#UCAP-CONTENT', '.article-content', '.article_content',
    '.content', '.zw_content', '.TRS_PreAppend', '.Custom_UnionStyle',
    '.xxgk_content', '.detail-content', '.news-content', 'article',
    '.main-content', '#content', '.con', '.bt_content', '.nr', '.main',
]
BATCH_SIZE = 30  # 每批处理条数，之后重启浏览器
PAGE_TIMEOUT = 45000  # 单页超时 ms
CONCURRENT_TABS = 2  # 并发 tab 数（共享一个浏览器实例）


def extract_content(html: str) -> str | None:
    """从 HTML 提取正文。"""
    soup = parse_html(html)
    for sel in CONTENT_SELECTORS:
        try:
            text = extract_by_selector(soup, sel)
            if text and len(text.strip()) > 100:
                return text[:200000]
        except Exception:
            continue
    # fallback: body text
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    body = soup.get_text('\n', strip=True)
    return body[:200000] if len(body) > 200 else None


async def try_httpx(url: str) -> str | None:
    """先试 httpx（快、省内存）。"""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as c:
            r = await c.get(url)
            if len(r.text) > 500:  # 放宽：403 页面也可能返回有效 HTML
                return r.text
    except Exception:
        pass
    return None


async def try_playwright(browser, url: str) -> str | None:
    """Playwright 抓取（慢但能绕过 WAF）。"""
    page = None
    try:
        page = await browser.new_page()
        await page.goto(url, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT)
        # 额外等 2 秒让 JS 渲染
        await asyncio.sleep(2)
        html = await page.content()
        return html if len(html) > 300 else None
    except Exception as e:
        logger.debug(f'PW fail: {str(e)[:60]}')
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def process_one(pol: Policy, browser, sem: asyncio.Semaphore, stats: dict) -> None:
    """处理单条政策。"""
    async with sem:
        html = await try_httpx(pol.url)
        method = 'httpx'

        if not html and browser:
            html = await try_playwright(browser, pol.url)
            method = 'playwright'

        content = extract_content(html) if html else None

        if content:
            async with get_session() as session:
                await session.execute(
                    update(Policy).where(Policy.id == pol.id).values(
                        raw_content=content,
                        full_text_fetched_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
            stats['ok'] += 1
            logger.info(f'OK #{pol.id} [{method}] {len(content)}chars')
        else:
            stats['fail'] += 1


async def process_batch(policies: list[Policy], browser) -> tuple[int, int]:
    """并发处理一批政策。返回 (success, fail)。"""
    stats = {'ok': 0, 'fail': 0}
    sem = asyncio.Semaphore(CONCURRENT_TABS)
    tasks = [process_one(p, browser, sem, stats) for p in policies]
    await asyncio.gather(*tasks)
    return stats['ok'], stats['fail']


async def run_all(limit: int = 0):
    engine = make_engine()
    init_session_factory(engine)

    # 查询所有空正文
    async with get_session() as session:
        stmt = select(Policy).where(
            (Policy.raw_content.is_(None)) | (Policy.raw_content == '')
        ).where(Policy.url.notlike('mock://%'))
        if limit > 0:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        all_policies = result.scalars().all()

    total = len(all_policies)
    logger.info(f'Total empty: {total} | Batch size: {BATCH_SIZE}')

    total_ok, total_fail = 0, 0
    playwright = None
    browser = None

    try:
        # 启动 Playwright（整个回填期间复用）
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)

        for i in range(0, total, BATCH_SIZE):
            batch = all_policies[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            # 每 BATCH_SIZE*3 条重启浏览器（防止内存泄漏）
            if i > 0 and i % (BATCH_SIZE * 3) == 0:
                logger.info(f'Restarting browser at batch {batch_num}...')
                await browser.close()
                browser = await playwright.chromium.launch(headless=True)

            ok, fail = await process_batch(batch, browser)
            total_ok += ok
            total_fail += fail
            await asyncio.sleep(1)  # 批次间短暂休息
            logger.info(f'Batch {batch_num}: +{ok} ok, +{fail} fail | Total: {total_ok}/{total_ok+total_fail} ({int(total_ok/(total_ok+total_fail)*100) if (total_ok+total_fail) > 0 else 0}%)')

    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

    logger.info(f'DONE: {total_ok} success, {total_fail} fail out of {total}')
    return total_ok, total_fail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='Limit policies to process')
    args = parser.parse_args()
    asyncio.run(run_all(limit=args.limit))


if __name__ == '__main__':
    main()
