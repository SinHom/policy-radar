"""回填 v3：先快速探测域名可达性，跳过死站，仅回填可达 URL。"""
import sys
sys.path.insert(0, '/app')

import sqlite3, time
from urllib.parse import urlparse
from urllib.request import urlopen, Request
import ssl
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DB = '/app/data/policy_radar.db'
TIMEOUT = 30000
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

    # Phase 1: 快速探测域名可达性（urllib，5s 超时）
    print(f'Total empty: {len(rows)}')
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    domain_ok = {}
    for _, url in rows:
        d = urlparse(url).netloc
        if d not in domain_ok:
            try:
                req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urlopen(req, timeout=5, context=ssl_ctx)
                html = resp.read().decode('utf-8', errors='ignore')
                domain_ok[d] = len(html) > 500
            except:
                domain_ok[d] = False
    ok_domains = {d for d, ok in domain_ok.items() if ok}
    dead_domains = {d for d, ok in domain_ok.items() if not ok}
    print(f'OK domains: {len(ok_domains)}')
    for d in sorted(ok_domains):
        print(f'  + {d}')
    print(f'DEAD domains: {len(dead_domains)}')
    for d in sorted(dead_domains):
        print(f'  - {d}')

    # Phase 2: 仅回填可达域名的 URL
    reachable = [(pid, url) for pid, url in rows if urlparse(url).netloc in ok_domains]
    unreachable = len(rows) - len(reachable)
    print(f'\nReachable: {len(reachable)}, Unreachable: {unreachable}')

    if not reachable:
        print('No reachable URLs, done.')
        return

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ok = fail = 0
    total = len(reachable)

    for i, (pid, url) in enumerate(reachable):
        page = None
        try:
            page = browser.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT)
            page.wait_for_timeout(2000)
            html = page.content()
            text = extract(html)
            if text:
                db = sqlite3.connect(DB)
                db.execute("UPDATE policies SET raw_content=?, full_text_fetched_at=? WHERE id=?",
                           (text, datetime.now(timezone.utc).isoformat(), pid))
                db.commit()
                db.close()
                ok += 1
                print(f'OK {i+1}/{total} #{pid} {len(text)}chars')
            else:
                fail += 1
                print(f'NO {i+1}/{total} #{pid} no_content')
        except Exception as e:
            fail += 1
            print(f'ERR {i+1}/{total} #{pid} {str(e)[:80]}')
        finally:
            if page:
                try: page.close()
                except: pass

        if (i + 1) % 50 == 0:
            browser.close()
            browser = pw.chromium.launch(headless=True)
            print(f'--- restart {i+1}/{total} ---')

    browser.close()
    pw.stop()
    print(f'DONE: ok={ok} fail={fail} reachable={total} skipped_dead={unreachable}')

if __name__ == '__main__':
    main()
