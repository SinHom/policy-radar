"""回填 v4：httpx 快速抓，3秒超时，失败跳过。简单粗暴。"""
import sys
sys.path.insert(0, '/app')

import sqlite3
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import httpx

DB = '/app/data/policy_radar.db'
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

    ok = fail = skip = 0
    client = httpx.Client(timeout=8, follow_redirects=True, verify=False,
                          headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'})

    for i, (pid, url) in enumerate(rows):
        try:
            resp = client.get(url)
            if resp.status_code >= 400 or len(resp.text) < 500:
                skip += 1
                if (i+1) % 50 == 0:
                    print(f'... {i+1}/{total} ok={ok} skip={skip} fail={fail}')
                continue

            text = extract(resp.text)
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
                print(f'NO {i+1}/{total} #{pid} no_extract')
        except Exception as e:
            skip += 1
            if (i+1) % 20 == 0:
                print(f'... {i+1}/{total} ok={ok} skip={skip} fail={fail}')

    client.close()
    print(f'DONE: ok={ok} skip={skip} fail={fail} total={total}')

if __name__ == '__main__':
    main()
