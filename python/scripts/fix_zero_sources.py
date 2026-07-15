"""批量修复零数据源的 spider config。

问题分类：
1. 缺少 config 文件（national_* 系列）
2. list_url 是首页（需要替换为具体子页面）
3. render_js=false 的源
4. RSSHub 源需要本地 RSSHub 服务
5. 内容类型子源找到 0 条（需要调整 selector）

用法：
    python -m scripts.fix_zero_sources --dry-run    # 只诊断不修改
    python -m scripts.fix_zero_sources              # 执行修复
    python -m scripts.fix_zero_sources --crawl      # 修复后立即爬取
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
logger = logging.getLogger("fix_zero")

SPIDERS_DIR = Path(__file__).resolve().parent.parent / "crawlers" / "spiders"

# ---- 已知的首页→通知公告页映射 ----
HOMEPAGE_TO_TZGG: dict[str, str] = {
    # 河北省厅局
    "http://gat.hebei.gov.cn/": "http://gat.hebei.gov.cn/tzgg/",
    "http://sft.hebei.gov.cn/": "http://sft.hebei.gov.cn/tzgg/",
    "http://jyt.hebei.gov.cn/": "http://jyt.hebei.gov.cn/tzgg/",
    "http://wenwu.hebei.gov.cn/": "http://wenwu.hebei.gov.cn/tzgg/",
    "http://swt.hebei.gov.cn/nx_html/tzwg/": "http://swt.hebei.gov.cn/nx_html/tzwg/",  # already tz
    "http://wsjkw.hebei.gov.cn/tzgg/": "http://wsjkw.hebei.gov.cn/tzgg/",  # already tzgg
    "https://zfcxjst.hebei.gov.cn/hbzjt/zcwj/gggs/index.html": "https://zfcxjst.hebei.gov.cn/hbzjt/zcwj/gggs/index.html",  # already gggs
    # 秦皇岛市局
    "http://jtj.qhd.gov.cn/": "http://jtj.qhd.gov.cn/tzgg/",
    "http://zjj.qhd.gov.cn/": "http://zjj.qhd.gov.cn/tzgg/",
    "http://nyncj.qhd.gov.cn/": "http://nyncj.qhd.gov.cn/tzgg/",
    "http://fgw.qhd.gov.cn/": "http://fgw.qhd.gov.cn/tzgg/",
    "http://scjg.qhd.gov.cn/": "http://scjg.qhd.gov.cn/tzgg/",
    "http://sthjj.qhd.gov.cn/": "http://sthjj.qhd.gov.cn/tzgg/",
    "http://kjj.qhd.gov.cn/": "http://kjj.qhd.gov.cn/tzgg/",
    "http://czj.qhd.gov.cn/": "http://czj.qhd.gov.cn/tzgg/",
    "http://www.qhd.gov.cn/": "http://www.qhd.gov.cn/tzgg/",
    # 深圳
    "https://stic.sz.gov.cn/xxgk/zcfg/index.html": "https://stic.sz.gov.cn/xxgk/zcfg/index.html",  # already zcfg
    # 其他
    "https://www.most.gov.cn/index.html": "https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/gfxwj/",
}


def get_spider_dir() -> Path:
    return SPIDERS_DIR


async def probe_url(client: httpx.AsyncClient, url: str) -> bool:
    """探测 URL 是否可访问。"""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15.0)
        return 200 <= resp.status_code < 300 and len(resp.text) > 500
    except Exception:
        return False


async def fix_missing_configs(dry_run: bool = False) -> list[str]:
    """为缺失 config 文件的 national_* 源创建配置。"""
    missing_map = {
        "national_gov_cn": {
            "source_id": "national_gov_cn",
            "name": "国务院",
            "list_url": "https://www.gov.cn/zhengce/index.htm",
            "category": "国家级",
            "region": "全国",
            "department": "国务院",
        },
        "national_miit": {
            "source_id": "national_miit",
            "name": "工信部",
            "list_url": "https://www.miit.gov.cn/search/wjfb.html",
            "category": "国家级",
            "region": "全国",
            "department": "工信部",
        },
        "national_most": {
            "source_id": "national_most",
            "name": "科技部",
            "list_url": "https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/fgzc/gfxwj/",
            "category": "国家级",
            "region": "全国",
            "department": "科技部",
        },
        "national_mof": {
            "source_id": "national_mof",
            "name": "财政部",
            "list_url": "http://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/",
            "category": "国家级",
            "region": "全国",
            "department": "财政部",
        },
    }

    created = []
    for sid, info in missing_map.items():
        path = SPIDERS_DIR / f"{sid}.json"
        if path.exists():
            logger.info("已存在: %s", sid)
            continue

        cfg = {
            **info,
            "mode": "html",
            "render_js": True,
            "frequency": "daily",
            "request_interval_min": 3,
            "request_interval_max": 6,
            "max_pages": 2,
            "list_selectors": {
                "item": "ul li",
                "title": "a::text",
                "href": "a::attr(href)",
                "date": "span::text",
            },
            "detail_selectors": {
                "title": "h1, .article-title, .bt, meta[name=\"ArticleTitle\"]",
                "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .TRS_PreAppend, .Custom_UnionStyle, .zw_content, article",
                "date": "meta[name=\"PubDate\"], .date, .info span, .pub-date, .article-date",
            },
            "notes": "自动生成·国家级·修复零数据源",
        }

        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            logger.info("创建: %s", sid)
        else:
            logger.info("[DRY RUN] 将创建: %s", sid)
        created.append(sid)

    return created


async def fix_homepage_sources(dry_run: bool = False) -> list[tuple[str, str, str]]:
    """修复 list_url 为首页的源，替换为通知公告页。"""
    fixed = []

    for old_url, new_url in HOMEPAGE_TO_TZGG.items():
        # 找到使用该 URL 的 source
        import sqlite3
        from python.models.base import make_engine

        engine = make_engine()
        db_path = engine.url.database
        conn = sqlite3.connect(db_path)
        rows = conn.execute('''
            SELECT s.source_id, s.name, s.spider_config
            FROM policy_sources s
            WHERE json_extract(s.spider_config, "$.list_url") = ?
            AND s.id NOT IN (SELECT DISTINCT source_id FROM policies)
        ''', (old_url,)).fetchall()
        conn.close()

        for sid, name, cfg_json in rows:
            if old_url == new_url:
                # Already correct URL, just needs re-crawl
                continue

            try:
                cfg = json.loads(cfg_json)
            except Exception:
                cfg = {}

            cfg["list_url"] = new_url
            cfg["render_js"] = True
            cfg["notes"] = cfg.get("notes", "") + " | 自动修复:首页→通知公告"

            if not dry_run:
                path = SPIDERS_DIR / f"{sid}.json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                # 同时更新 DB
                import sqlite3 as sq
                conn2 = sq.connect(db_path)
                conn2.execute(
                    "UPDATE policy_sources SET spider_config = ?, last_status = 'pending' WHERE source_id = ?",
                    (json.dumps(cfg, ensure_ascii=False), sid),
                )
                conn2.commit()
                conn2.close()

            logger.info("%s %s: %s → %s",
                        "[DRY RUN]" if dry_run else "修复",
                        name, old_url[:60], new_url[:60])
            fixed.append((sid, name, new_url))

    return fixed


async def fix_render_js(dry_run: bool = False) -> list[str]:
    """将 render_js=false 的零数据源改为 true。"""
    import sqlite3
    from python.models.base import make_engine

    engine = make_engine()
    db_path = engine.url.database
    conn = sqlite3.connect(db_path)
    rows = conn.execute('''
        SELECT s.source_id, s.name, s.spider_config
        FROM policy_sources s
        WHERE s.enabled = 1
        AND s.id NOT IN (SELECT DISTINCT source_id FROM policies)
        AND json_extract(s.spider_config, "$.render_js") = 0
        AND json_extract(s.spider_config, "$.mode") != "rss"
    ''').fetchall()
    conn.close()

    fixed = []
    for sid, name, cfg_json in rows:
        try:
            cfg = json.loads(cfg_json)
        except Exception:
            continue

        cfg["render_js"] = True
        cfg["notes"] = cfg.get("notes", "") + " | 自动修复:render_js=true"

        if not dry_run:
            path = SPIDERS_DIR / f"{sid}.json"
            if path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)

            conn2 = sqlite3.connect(db_path)
            conn2.execute(
                "UPDATE policy_sources SET spider_config = ?, last_status = 'pending' WHERE source_id = ?",
                (json.dumps(cfg, ensure_ascii=False), sid),
            )
            conn2.commit()
            conn2.close()

        logger.info("%s %s: render_js=false → true", "[DRY RUN]" if dry_run else "修复", name)
        fixed.append(sid)

    return fixed


async def fix_all(dry_run: bool = False, crawl: bool = False) -> dict:
    """执行所有修复。"""
    stats = {"missing_configs": 0, "homepage_fixed": 0, "render_js_fixed": 0, "total_crawled": 0}

    # 1. 创建缺失的 config
    created = await fix_missing_configs(dry_run=dry_run)
    stats["missing_configs"] = len(created)

    # 2. 修复首页→通知公告
    fixed_home = await fix_homepage_sources(dry_run=dry_run)
    stats["homepage_fixed"] = len(fixed_home)

    # 3. 修复 render_js
    fixed_js = await fix_render_js(dry_run=dry_run)
    stats["render_js_fixed"] = len(fixed_js)

    # 4. 可选：立即爬取
    if crawl and not dry_run:
        all_fixed = [c for c in created] + [f[0] for f in fixed_home] + fixed_js
        all_fixed = list(set(all_fixed))  # dedup
        if all_fixed:
            logger.info("开始爬取 %d 个修复后的源...", len(all_fixed))
            from python.crawlers.engine import run_crawler
            results = await run_crawler(source_ids=all_fixed, max_new_per_source=10)
            stats["total_crawled"] = sum(r.new_crawled for r in results)
            logger.info("爬取完成: +%d 新政策", stats["total_crawled"])

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="批量修复零数据源")
    parser.add_argument("--dry-run", action="store_true", help="只诊断不修改")
    parser.add_argument("--crawl", action="store_true", help="修复后立即爬取")
    parser.add_argument("--skip-crawl", action="store_true", help="只修复不爬取")
    args = parser.parse_args()

    do_crawl = args.crawl and not args.skip_crawl
    stats = asyncio.run(fix_all(dry_run=args.dry_run, crawl=do_crawl))

    print(f"\n修复统计: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
