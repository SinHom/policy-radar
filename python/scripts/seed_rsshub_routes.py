"""Seed 已 work 的 RSSHub gov/* 路由(2026-06-29 探测结果:HTTP 200 + items>0)。

为每个 work 路由:
1. DB INSERT 一行 policy_sources(source_id, name, region/dept/category)
2. 在 spiders/ 下生成 spider.json(mode='rss', list_url=policy-radar-rsshub + path)
3. 已有 source 跳过 DB insert(避免重复)

跑法(容器内):
    docker exec policy-radar-app python /app/python/scripts/seed_rsshub_routes.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# 已知 work 的 10 个 gov 路由(source_id, name, region, dept, category, rss_path)
# 来自 2026-06-29 手动探测:HTTP 200 + items>0
WORK_ROUTES = [
    ("gov_ndrc_zfxxgk",      "国家发改委 政务公开",          "全国", "发改委",     "国家级", "/gov/ndrc/zfxxgk"),
    ("gov_mof_gss",           "财政部 工交司",                "全国", "财政部",     "国家级", "/gov/mof/gss"),
    ("gov_mee_ywdt",          "生态环境部 新闻动态",          "全国", "生态环境部", "国家级", "/gov/mee/ywdt/hjywnews"),
    ("gov_pbc_zcyj",          "中国人民银行 政策研究",        "全国", "央行",       "国家级", "/gov/pbc/zcyj"),
    ("gov_pbc_gzlw",          "中国人民银行 工作论文",        "全国", "央行",       "国家级", "/gov/pbc/gzlw"),
    ("gov_chinatax_latest",   "国家税务总局 最新政策",        "全国", "税务总局",   "国家级", "/gov/chinatax/latest"),
    ("gov_moa_szcpxx",        "农业农村部 农产品质量安全",    "全国", "农业农村部", "国家级", "/gov/moa/szcpxx"),
    ("gov_stats",             "国家统计局 新闻",              "全国", "统计局",     "国家级", "/gov/stats"),
    ("gov_cnnic",             "中国互联网络中心",            "全国", "CNNIC",      "国家级", "/gov/cnnic"),
    ("gov_zhengce_zfxxgk",    "中国政府网 政务公开",          "全国", "国务院",     "国家级", "/gov/zhengce/zfxxgk"),
]

DB_PATH = "/app/data/policy_radar.db"
RSS_BASE = "http://policy-radar-rsshub:1200"
SPIDERS_DIR = Path("/app/python/crawlers/spiders")


def main() -> None:
    c = sqlite3.connect(DB_PATH)
    insert_count = skip_count = spider_count = 0
    for sid, name, region, dept, category, path in WORK_ROUTES:
        # 1) DB INSERT(已存在跳过)
        existing = c.execute(
            "SELECT id FROM policy_sources WHERE source_id = ?", (sid,)
        ).fetchone()
        if existing:
            skip_count += 1
            print(f"  skip {sid} (DB 已存在)")
        else:
            c.execute(
                """INSERT INTO policy_sources
                   (source_id, name, url, category, region, department,
                    spider_config, frequency, enabled, last_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'daily', 1, 'pending', ?)""",
                (sid, name, RSS_BASE + path, category, region, dept, "{}",
                 __import__("datetime").datetime.utcnow().isoformat()),
            )
            insert_count += 1
            print(f"  + inserted {sid}")

        # 2) spider.json(load_spider_config 动态读,只缺不补)
        spider_path = SPIDERS_DIR / f"{sid}.json"
        if not spider_path.exists():
            spider = {
                "source_id": sid,
                "name": name,
                "category": category,
                "list_url": RSS_BASE + path,
                "mode": "rss",
                "render_js": False,
                "frequency": "daily",
                "request_interval_min": 3,
                "request_interval_max": 5,
                "max_pages": 1,
                "notes": f"RSSHub {path} (服务端 RSSHub 路由,RSS mode)",
            }
            spider_path.write_text(
                json.dumps(spider, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            spider_count += 1
            print(f"  wrote {spider_path}")
        else:
            print(f"  spider 存在 {spider_path}")

    c.commit()
    c.close()
    print(f"\n总结: DB 插入 {insert_count} / 跳过 {skip_count}; spider 新建 {spider_count}")


if __name__ == "__main__":
    main()
