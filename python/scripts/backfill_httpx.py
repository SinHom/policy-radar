"""轻量回填：用 httpx（不用 Playwright）批量填正文。适合服务器端（国内 IP 可直连政府站）。"""

import asyncio, sys, logging
sys.path.insert(0, '/app')

from sqlalchemy import select, update
from python.models import Policy
from python.models.base import get_session, init_session_factory, make_engine
from python.crawlers.parser import parse_html, extract_by_selector
from datetime import datetime, timezone
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bf_httpx")

SELECTORS = [
    '.TRS_Editor', '#UCAP-CONTENT', '.article-content', '.article_content',
    '.content', '.zw_content', '.TRS_PreAppend', '.Custom_UnionStyle',
    '.xxgk_content', '.detail-content', '.news-content', 'article',
    '.main-content', '#content', '.text-content', '.con', '.bt_content', '.nr', '.main',
]

async def run(limit: int = 100, offset: int = 0):
    engine = make_engine()
    init_session_factory(engine)

    async with get_session() as session:
        result = await session.execute(
            select(Policy)
            .where((Policy.raw_content.is_(None)) | (Policy.raw_content == ''))
            .where(Policy.url.notlike('mock://%'))
            .limit(limit).offset(offset)
        )
        rows = result.scalars().all()

    logger.info(f'Target: {len(rows)} policies (offset={offset})')

    success = fail = 0
    timeout = httpx.Timeout(30.0, connect=10.0)
    limits = httpx.Limits(max_connections=10)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True, verify=False) as client:
        sem = asyncio.Semaphore(5)

        async def process(pol: Policy):
            nonlocal success, fail
            async with sem:
                try:
                    resp = await client.get(pol.url)
                    if resp.status_code != 200 or len(resp.text) < 200:
                        fail += 1
                        return
                    soup = parse_html(resp.text)
                    content = None
                    for sel in SELECTORS:
                        extracted = extract_by_selector(soup, sel)
                        if extracted and len(extracted.strip()) > 100:
                            content = extracted[:200000]
                            break
                    if not content:
                        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                            tag.decompose()
                        body_text = soup.get_text('\n', strip=True)
                        if len(body_text) > 200:
                            content = body_text[:200000]
                    if not content:
                        fail += 1
                        return

                    async with get_session() as session:
                        await session.execute(
                            update(Policy).where(Policy.id == pol.id).values(
                                raw_content=content,
                                full_text_fetched_at=datetime.now(timezone.utc),
                            )
                        )
                        await session.commit()
                    success += 1
                except Exception as e:
                    fail += 1
                    logger.debug(f'FAIL #{pol.id}: {str(e)[:60]}')

        tasks = [process(p) for p in rows]
        await asyncio.gather(*tasks)

    logger.info(f'Done: success={success} fail={fail}')
    return success, fail


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--all', action='store_true', help='Process all remaining')
    args = parser.parse_args()

    if args.all:
        total_s, total_f = 0, 0
        while True:
            s, f = asyncio.run(run(limit=200, offset=0))
            total_s += s; total_f += f
            logger.info(f'Batch done: +{s} success, +{f} fail | Total: {total_s}/{total_s+total_f}')
            remaining = total_s + total_f
            if remaining == 0 or (s == 0 and f == 0):
                break
        logger.info(f'ALL DONE: total processed={total_s+total_f}, success={total_s}, fail={total_f}')
    else:
        asyncio.run(run(limit=args.limit, offset=args.offset))
