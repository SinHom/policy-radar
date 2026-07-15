"""探测各政府站的子页面（通知公告/政策解读/公示），自动生成 spider config。

用法：
    python -m scripts.probe_content_types              # 探测所有working源
    python -m scripts.probe_content_types --dry-run    # 只探测不创建
    python -m scripts.probe_content_types --type tzgg  # 只探测通知公告
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("probe_ct")

SPIDERS_DIR = Path(__file__).resolve().parent.parent / "crawlers" / "spiders"

# 内容类型 → 常见 URL 后缀模式
CONTENT_TYPE_PATTERNS = {
    "tzgg": [
        "/tzgg/", "/tzgg/index.html", "/tzgg/index.htm",
        "/tz/", "/tz/index.html",
        "/tzgg_1120/", "/tzgg83/",
        "/tongzhigonggao/", "/tongzhigonggao/index.html",
        "/xwzx/tzgg/", "/zwgk/tzgg/", "/xxgk/tzgg/",
        "/gk/tzgg/", "/gk/xxgk/tzgg/",
        "/category/tzgg", "/list/tzgg",
        "/a/ZX/tzgg/",
        "/node/",  # some use node IDs
    ],
    "zcjd": [
        "/zcjd/", "/zcjd/index.html",
        "/zhengcejiedu/", "/zhengcejiedu/index.html",
        "/zwgk/zcjd/", "/xxgk/zcjd/",
        "/gk/zcjd/",
    ],
    "gs": [
        "/gs/", "/gs/index.html",
        "/gggs/", "/gggs/index.html",
        "/gongshi/", "/gongshi/index.html",
        "/xxgk/gs/", "/zwgk/gs/",
    ],
}

# 已有的内容类型（避免重复创建）
EXISTING_PATTERNS = {
    "tzgg": ["tzgg", "tz/", "tongzhigonggao", "通知公告", "通知"],
    "zcjd": ["zcjd", "zhengcejiedu", "政策解读"],
    "gs": ["/gs/", "gggs", "gongshi", "公示"],
}


async def probe_url(client: httpx.AsyncClient, url: str) -> tuple[str, bool, int]:
    """探测 URL 是否可访问。返回 (url, ok, status_code)"""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15.0)
        # 200-299 且内容长度 > 500 字符
        if 200 <= resp.status_code < 300 and len(resp.text) > 500:
            return (url, True, resp.status_code)
        return (url, False, resp.status_code)
    except Exception:
        return (url, False, 0)


def has_content_type(list_url: str, ctype: str) -> bool:
    """检查 URL 是否已包含某种内容类型"""
    url_lower = list_url.lower()
    for pat in EXISTING_PATTERNS.get(ctype, []):
        if pat.lower() in url_lower:
            return True
    return False


def get_base_url(list_url: str) -> str:
    """从 list_url 提取 base URL (scheme + host)"""
    parsed = urlparse(list_url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def probe_source(
    client: httpx.AsyncClient,
    name: str,
    source_id: str,
    list_url: str,
    ctypes: list[str],
) -> list[dict]:
    """探测单个源的子页面。返回可创建 config 的列表。"""
    results = []
    base = get_base_url(list_url)

    for ctype in ctypes:
        if has_content_type(list_url, ctype):
            logger.debug("[%s] 已有 %s 类型，跳过", name, ctype)
            continue

        patterns = CONTENT_TYPE_PATTERNS.get(ctype, [])
        found = False
        for pat in patterns[:10]:  # 只试前 10 个最常见模式
            test_url = urljoin(base, pat)
            url, ok, status = await probe_url(client, test_url)
            if ok:
                logger.info("[%s] ✓ %s → %s (%d)", name, ctype, url, status)
                results.append({
                    "source_id": f"{source_id}_{ctype}",
                    "name": f"{name}·{ctype}",
                    "type": ctype,
                    "list_url": url,
                    "base_source": source_id,
                })
                found = True
                break
        if not found:
            logger.debug("[%s] ✗ %s 未找到", name, ctype)

    return results


def create_spider_config(probe_result: dict, base_config: dict) -> dict:
    """基于探测结果和基础 config 创建新的 spider config。"""
    cfg = {
        "source_id": probe_result["source_id"],
        "name": probe_result["name"],
        "category": base_config.get("category", "省级"),
        "region": base_config.get("region", ""),
        "department": base_config.get("department", ""),
        "list_url": probe_result["list_url"],
        "mode": "html",
        "render_js": base_config.get("render_js", True),
        "frequency": "daily",
        "request_interval_min": base_config.get("request_interval_min", 3),
        "request_interval_max": base_config.get("request_interval_max", 6),
        "max_pages": base_config.get("max_pages", 2),
        "list_selectors": base_config.get("list_selectors", {
            "item": "ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text",
        }),
        "detail_selectors": base_config.get("detail_selectors", {
            "title": "h1, .article-title, .bt, meta[name=\"ArticleTitle\"]",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .TRS_PreAppend, .Custom_UnionStyle, .zw_content, article",
            "date": "meta[name=\"PubDate\"], .date, .info span, .pub-date, .article-date",
        }),
        "notes": f"自动生成·{probe_result['type']}·基于{probe_result['base_source']}",
    }
    return cfg


async def probe_all(
    ctypes: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """探测所有 working 源的子页面。"""
    import sqlite3
    from python.models.base import make_engine

    ctypes = ctypes or list(CONTENT_TYPE_PATTERNS.keys())

    # 连接 DB 获取 working 源
    engine = make_engine()
    db_path = engine.url.database
    conn = sqlite3.connect(db_path)
    rows = conn.execute('''
        SELECT s.source_id, s.name, s.spider_config, json_extract(s.spider_config, "$.list_url") as list_url
        FROM policy_sources s
        WHERE s.enabled = 1
        AND s.id IN (SELECT DISTINCT source_id FROM policies)
        AND json_extract(s.spider_config, "$.mode") != "rss"
        ORDER BY s.name
    ''').fetchall()
    conn.close()

    logger.info("探测 %d 个信源的子页面: %s", len(rows), ctypes)

    limits = httpx.Limits(max_connections=5)
    async with httpx.AsyncClient(limits=limits, timeout=30.0) as client:
        all_results = []
        for sid, name, cfg_json, list_url in rows:
            if not list_url:
                continue
            try:
                cfg = json.loads(cfg_json)
            except Exception:
                cfg = {}
            results = await probe_source(client, name, sid, list_url, ctypes)
            all_results.extend(results)
            # 限速
            await asyncio.sleep(0.5)

    # 创建 spider configs
    created = 0
    for r in all_results:
        # 加载基础 config
        base_path = SPIDERS_DIR / f"{r['base_source']}.json"
        if base_path.exists():
            try:
                with open(base_path, encoding="utf-8") as f:
                    base_cfg = json.load(f)
            except Exception:
                base_cfg = {}
        else:
            base_cfg = {}

        new_cfg = create_spider_config(r, base_cfg)
        new_path = SPIDERS_DIR / f"{r['source_id']}.json"

        if new_path.exists():
            logger.info("跳过已存在: %s", r['source_id'])
            continue

        if not dry_run:
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(new_cfg, f, ensure_ascii=False, indent=2)
            logger.info("创建: %s → %s", r['source_id'], r['list_url'][:80])
        else:
            logger.info("[DRY RUN] 将创建: %s → %s", r['source_id'], r['list_url'][:80])
        created += 1

    stats = {
        "total_sources": len(rows),
        "found_pages": len(all_results),
        "created_configs": created,
        "dry_run": dry_run,
    }
    logger.info("探测完成: %s", stats)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="探测政府站子页面并生成 spider config")
    parser.add_argument("--dry-run", action="store_true", help="只探测不创建文件")
    parser.add_argument("--type", dest="ctypes", type=str, default=None,
                        help="内容类型，逗号分隔（如 'tzgg,zcjd'），默认全部")
    args = parser.parse_args()

    ctypes = None
    if args.ctypes:
        ctypes = [t.strip() for t in args.ctypes.split(",")]

    stats = asyncio.run(probe_all(ctypes=ctypes, dry_run=args.dry_run))
    print(f"\n探测统计: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
