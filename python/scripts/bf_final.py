"""回填终版：Playwright 单浏览器，遇超时 URL 记入黑名单跳过。"""
import sys
sys.path.insert(0, '/app')

import sqlite3, json
from datetime import datetime, timezone
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

DB = '/app/data/policy_radar.db'
DEAD_FILE = '/app/data/dead_domains.json'
TIMEOUT = 25000  # 25s per page
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


def load_dead():
    try:
        with open(DEAD_FILE) as f:
            return set(json.load(f))
    except:
        return set()


def save_dead(dead):
    with open(DEAD_FILE, 'w') as f:
        json.dump(sorted(dead), f)


def main():
    dead = load_dead()
    db = sqlite3.connect(DB)
    rows = db.execute(
        "SELECT id, url FROM policies WHERE (raw_content IS NULL OR raw_content='') AND url NOT LIKE 'mock://%'"
    ).fetchall()
    db.close()

    # 过滤死域名
    rows = [(pid, url) for pid, url in rows if urlparse(url).netloc not in dead]
    total = len(rows)
    print(f'Empty: {total} (skipped {len(dead)} dead domains)')

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ok = fail = skip = 0

    for i, (pid, url) in enumerate(rows):
        domain = urlparse(url).netloc
        if domain in dead:
            skip += 1
            continue

        page = None
        try:
            page = browser.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT)
            page.wait_for_timeout(1500)
            html = page.content()

            if len(html) < 500:
                fail += 1
                continue

            text = extract(html)
            if text:
                db = sqlite3.connect(DB)
                db.execute("UPDATE policies SET raw_content=?, full_text_fetched_at=? WHERE id=?",
                           (text, datetime.now(timezone.utc).isoformat(), pid))
                db.commit()
                db.close()
                ok += 1
                print(f'OK {i+1}/{total} #{pid} [{domain}] {len(text)}chars')
            else:
                fail += 1
                print(f'NO {i+1}/{total} #{pid} [{domain}]')
        except PwTimeout:
            # 域名彻底不可达，加入黑名单
            dead.add(domain)
            save_dead(dead)
            skip += 1
            print(f'DEAD {i+1}/{total} #{pid} [{domain}] -> blacklisted ({len(dead)} total)')
        except Exception as e:
            fail += 1
            err = str(e)[:60]
            print(f'ERR {i+1}/{total} #{pid} {err}')
        finally:
            if page:
                try: page.close()
                except: pass

        if (i + 1) % 50 == 0:
            browser.close()
            browser = pw.chromium.launch(headless=True)
            print(f'--- restart {i+1}/{total} ok={ok} fail={fail} skip={skip} dead_domains={len(dead)} ---')

    browser.close()
    pw.stop()
    print(f'DONE: ok={ok} fail={fail} skip={skip} dead_domains={len(dead)}')

if __name__ == '__main__':
    main()
