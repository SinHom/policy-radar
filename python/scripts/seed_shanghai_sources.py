"""为上海市所有委办局 + 区创建 spider config 并 seed 到 DB。

上海政府站 URL 模式：
- 委办局: https://XXX.shanghai.gov.cn/（子域名）
- 区: https://www.XXX.gov.cn/ 或 https://www.shXXX.gov.cn/
- 大部分站点封锁非大陆 IP（需从服务器端爬取）

用法：
    python -m scripts.seed_shanghai_sources          # 仅创建 config 文件
    python -m scripts.seed_shanghai_sources --seed   # 创建 config + seed 到 DB
    python -m scripts.seed_shanghai_sources --crawl  # 创建 + seed + 爬取
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_sh")

SPIDERS_DIR = Path(__file__).resolve().parent.parent / "crawlers" / "spiders"

# ---- 上海市委办局完整清单 ----
# 格式: (source_id, 部门名, 子域名, 通知公告页路径)
SHANGHAI_DEPARTMENTS: list[dict] = [
    # 综合管理
    {"source_id": "sh_fgw", "name": "上海市发改委", "dept": "发改委", "host": "fgw.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jxw", "name": "上海市经信委", "dept": "经信委", "host": "sheitc.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_sww", "name": "上海市商务委", "dept": "商务委", "host": "sww.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_edu", "name": "上海市教委", "dept": "教委", "host": "edu.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_kw", "name": "上海市科委", "dept": "科委", "host": "stcsm.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_gaj", "name": "上海市公安局", "dept": "公安局", "host": "gaj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_mzj", "name": "上海市民政局", "dept": "民政局", "host": "mzj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_sfj", "name": "上海市司法局", "dept": "司法局", "host": "sfj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_czj", "name": "上海市财政局", "dept": "财政局", "host": "czj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_rsj", "name": "上海市人社局", "dept": "人社局", "host": "rsj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_zjw", "name": "上海市住建委", "dept": "住建委", "host": "zjw.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jtw", "name": "上海市交通委", "dept": "交通委", "host": "jtw.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_nyncw", "name": "上海市农业农村委", "dept": "农业农村委", "host": "nyncw.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_sthj", "name": "上海市生态环境局", "dept": "生态环境局", "host": "sthj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_ghzyj", "name": "上海市规自局", "dept": "规自局", "host": "ghzyj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_swj", "name": "上海市水务局", "dept": "水务局", "host": "swj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_wsjkw", "name": "上海市卫健委", "dept": "卫健委", "host": "wsjkw.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_sjj", "name": "上海市审计局", "dept": "审计局", "host": "sjj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_gzw", "name": "上海市国资委", "dept": "国资委", "host": "gzw.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_tjj", "name": "上海市统计局", "dept": "统计局", "host": "tjj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_tyj", "name": "上海市体育局", "dept": "体育局", "host": "tyj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_lhsr", "name": "上海市绿化市容局", "dept": "绿化市容局", "host": "lhsr.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_yjglj", "name": "上海市应急管理局", "dept": "应急管理局", "host": "yjglj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jgswj", "name": "上海市机关事务管理局", "dept": "机关事务管理局", "host": "jgswj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jrj", "name": "上海市金融局", "dept": "金融局", "host": "jrj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_ybj", "name": "上海市医保局", "dept": "医保局", "host": "ybj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_whlyj", "name": "上海市文旅局", "dept": "文旅局", "host": "whlyj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_scjgj", "name": "上海市市监局", "dept": "市监局", "host": "scjgj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_mzj_2", "name": "上海市民宗局", "dept": "民宗局", "host": "mzzjj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_wsb", "name": "上海市外办", "dept": "外办", "host": "wsb.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_hzjl", "name": "上海市合作交流办", "dept": "合作交流办", "host": "hzjl.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jyj", "name": "上海市监狱管理局", "dept": "监狱管理局", "host": "jyj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_kfq", "name": "上海市数据局", "dept": "数据局", "host": "dsj.shanghai.gov.cn", "tzgg": "/tzgg/"},
    # 市政府办公厅（政策发布平台）
    {"source_id": "sh_zhengce", "name": "上海市政府·政策发布", "dept": "市政府办公厅", "host": "www.shanghai.gov.cn", "tzgg": "/zhengce/list"},
]

# ---- 上海市 16 个区 ----
SHANGHAI_DISTRICTS: list[dict] = [
    {"source_id": "sh_pudong", "name": "浦东新区", "dept": "区政府", "host": "www.pudong.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_huangpu", "name": "黄浦区", "dept": "区政府", "host": "www.shhuangpu.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_xuhui", "name": "徐汇区", "dept": "区政府", "host": "www.xuhui.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_changning", "name": "长宁区", "dept": "区政府", "host": "www.shcn.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jingan", "name": "静安区", "dept": "区政府", "host": "www.jingan.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_putuo", "name": "普陀区", "dept": "区政府", "host": "www.shpt.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_hongkou", "name": "虹口区", "dept": "区政府", "host": "www.shhk.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_yangpu", "name": "杨浦区", "dept": "区政府", "host": "www.shyp.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_minhang", "name": "闵行区", "dept": "区政府", "host": "www.shmh.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_baoshan", "name": "宝山区", "dept": "区政府", "host": "www.shbs.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jiading", "name": "嘉定区", "dept": "区政府", "host": "www.jiading.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_jinshan", "name": "金山区", "dept": "区政府", "host": "www.jinshan.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_songjiang", "name": "松江区", "dept": "区政府", "host": "www.songjiang.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_qingpu", "name": "青浦区", "dept": "区政府", "host": "www.shqp.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_fengxian", "name": "奉贤区", "dept": "区政府", "host": "www.fengxian.gov.cn", "tzgg": "/tzgg/"},
    {"source_id": "sh_chongming", "name": "崇明区", "dept": "区政府", "host": "www.shcm.gov.cn", "tzgg": "/tzgg/"},
]


def make_spider_config(info: dict, category: str) -> dict:
    """生成 spider JSON 配置。"""
    list_url = f"https://{info['host']}{info['tzgg']}"
    return {
        "source_id": info["source_id"],
        "name": info["name"],
        "category": category,
        "region": "上海",
        "department": info.get("dept", ""),
        "list_url": list_url,
        "mode": "html",
        "render_js": True,  # 上海政府站大量 JS 渲染
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
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .TRS_PreAppend, .Custom_UnionStyle, .zw_content, article, .info-content, .xxgk_content",
            "date": "meta[name=\"PubDate\"], .date, .info span, .pub-date, .article-date",
        },
        "notes": f"上海市{category}·{info['dept']}·通知公告·需服务器端（封锁非大陆IP）",
    }


async def seed_to_db(source_ids: list[str]) -> int:
    """将新 config seed 到 DB。"""
    from sqlalchemy import select
    from python.models import PolicySource
    from python.models.base import get_session, init_session_factory, make_engine

    engine = make_engine()
    init_session_factory(engine)

    async with get_session() as session:
        existing = (await session.execute(
            select(PolicySource.source_id)
        )).scalars().all()
    existing_set = set(existing)

    new_ids = [s for s in source_ids if s not in existing_set]
    logger.info("新增 %d 个源, 已存在 %d 个", len(new_ids), len(source_ids) - len(new_ids))

    seeded = 0
    for sid in new_ids:
        path = SPIDERS_DIR / f"{sid}.json"
        if not path.exists():
            logger.warning("Config 文件缺失: %s", sid)
            continue
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)

        async with get_session() as session:
            src = PolicySource(
                source_id=sid,
                name=cfg.get("name", sid),
                url=cfg.get("list_url", ""),
                category=cfg.get("category", "市级"),
                department=cfg.get("department", ""),
                region="上海",
                spider_config=cfg,
                frequency="daily",
                enabled=True,
                last_status="pending",
            )
            session.add(src)
            await session.commit()
        seeded += 1

    return seeded


async def main(dry_run: bool = False, do_seed: bool = False, do_crawl: bool = False) -> dict:
    """主流程。"""
    all_sources: list[dict] = []

    # 委办局
    for d in SHANGHAI_DEPARTMENTS:
        cfg = make_spider_config(d, "市级")
        all_sources.append({"info": d, "config": cfg, "category": "市级"})

    # 区
    for d in SHANGHAI_DISTRICTS:
        cfg = make_spider_config(d, "区级")
        all_sources.append({"info": d, "config": cfg, "category": "区级"})

    logger.info("共 %d 个源（市级 %d + 区级 %d）",
                len(all_sources), len(SHANGHAI_DEPARTMENTS), len(SHANGHAI_DISTRICTS))

    # 写 config 文件
    created = 0
    for s in all_sources:
        sid = s["config"]["source_id"]
        path = SPIDERS_DIR / f"{sid}.json"
        if path.exists():
            logger.debug("跳过已存在: %s", sid)
            continue
        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(s["config"], f, ensure_ascii=False, indent=2)
            logger.info("创建: %s → %s", sid, s["config"]["list_url"])
        else:
            logger.info("[DRY RUN] %s → %s", sid, s["config"]["list_url"])
        created += 1

    stats = {"total": len(all_sources), "created": created, "seeded": 0, "crawled": 0}

    # Seed 到 DB
    if do_seed and not dry_run:
        all_ids = [s["config"]["source_id"] for s in all_sources]
        stats["seeded"] = await seed_to_db(all_ids)

    # 可选：立即爬取
    if do_crawl and not dry_run:
        logger.info("开始爬取上海信源（⚠️ 需服务器端，本地大概率 blocked）...")
        from python.crawlers.engine import run_crawler
        all_ids = [s["config"]["source_id"] for s in all_sources]
        results = await run_crawler(source_ids=all_ids, max_new_per_source=5)
        stats["crawled"] = sum(r.new_crawled for r in results)

    logger.info("完成: %s", stats)
    return stats


def cli() -> int:
    parser = argparse.ArgumentParser(description="批量创建上海市政策源 spider config")
    parser.add_argument("--dry-run", action="store_true", help="只预览不创建")
    parser.add_argument("--seed", action="store_true", help="同时 seed 到 DB")
    parser.add_argument("--crawl", action="store_true", help="同时爬取（需服务器端）")
    args = parser.parse_args()

    stats = asyncio.run(main(
        dry_run=args.dry_run,
        do_seed=args.seed,
        do_crawl=args.crawl,
    ))
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}统计: {json.dumps(stats, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(cli())
