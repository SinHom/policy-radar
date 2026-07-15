"""最简回填：单 Playwright 浏览器逐条抓取+入库。print 实时输出，不死寂。"""
import sys
sys.path.insert(0, '/app')

import sqlite3, time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DB = '/app/data/policy_radar.db'
TIMEOUT = 30000  # ms
SELECTORS = '.TRS_Editor,#UCAP-CONTENT,.article-content,.content,.zw_content,.xxgk_content,article,.main-content,#content,.con,.nr,.main'


def extract(html):
    soup = BeautifulSoup(html, 'lxml')
    for sel in SELECTORS.split(','):
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 100:
            return el.get_text('\n', strip=True)[:200000]
    for t in soup(['script', 'style', 'nav', 'footer', 'header']):
        t.decompose()
    body = soup.get_text('\n', strip=True)
    return body[:200000] if len(body) > 100 else None


def main():
    db = sqlite3.connect(DB)
    rows = db.execute(
        "SELECT id, url FROM policies WHERE (raw_content IS NULL OR raw_content='') AND url NOT LIKE 'mock://%'"
    ).fetchall()
    db.close()
    total = len(rows)
    print(f'Empty: {total}')

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ok = fail = 0

    for i, (pid, url) in enumerate(rows):
        page = None
        try:
            page = browser.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT)
            page.wait_for_timeout(2000)
            html = page.content()
            text = extract(html)
            if text:
                db = sqlite3.connect(DB)
                db.execute(
                    "UPDATE policies SET raw_content=?, full_text_fetched_at=? WHERE id=?",
                    (text, datetime.now(timezone.utc).isoformat(), pid)
                )
                db.commit()
                db.close()
                ok += 1
                print(f'OK {i+1}/{total} #{pid} {len(text)}chars')
            else:
                fail += 1
                print(f'NO {i+1}/{total} #{pid} no_content')
        except Exception as e:
            fail += 1
            print(f'ERR {i+1}/{total} #{pid} {str(e)[:60]}')
        finally:
            if page:
                try: page.close()
                except: pass

        # 每 50 条重启浏览器防泄漏
        if (i + 1) % 50 == 0:
            browser.close()
            browser = pw.chromium.launch(headless=True)
            print(f'--- restart browser at {i+1}/{total} ---')

    browser.close()
    pw.stop()
    print(f'DONE: ok={ok} fail={fail} total={total}')

if __name__ == '__main__':
    main()
