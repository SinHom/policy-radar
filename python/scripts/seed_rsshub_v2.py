"""Seed RSSHub gov/* 路由 → policy_sources 表(基于 rsshub_gov_paths.json)。

覆盖范围:117 个可探测 example 路由,自动分类(国家级/省级/市级/区县)+ 提取 region/department。

跑法(容器内):
    docker exec policy-radar-app python /app/python/scripts/seed_rsshub_v2.py [--probe]
    --probe: 跑完 seed 后批量 HTTP 探测,失败的 source 标记 last_status='failed'
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# 国家级部委映射(file top-level → 中文部门名)
NATIONAL_DEPT = {
    "cac": "网信办", "ccdi": "中纪委", "chinamine-safety": "矿山安全监察局",
    "chinatax": "税务总局", "cmse": "证监会", "cnnic": "互联网络中心",
    "csrc": "证监会", "customs": "海关总署", "forestry": "林草局",
    "jgjcndrc": "发改委(价格)", "lswz": "粮食和物资储备局",
    "mee": "生态环境部", "mem": "应急管理部", "mfa": "外交部",
    "mgs": "自然资源部", "miit": "工信部", "mmht": "国家民委",
    "moa": "农业农村部", "moe": "教育部", "mof": "财政部",
    "mofcom": "商务部", "moj": "司法部", "mot": "交通运输部",
    "ndrc": "发改委", "nea": "国家能源局", "nfra": "金融监管总局",
    "nifdc": "国家药监局", "nmpa": "药监局", "nopss": "哲学社会科学",
    "npc": "全国人大", "nppa": "新闻出版署", "nrta": "广电总局",
    "nsfc": "国家自然科学基金委", "pbc": "央行", "safe": "外汇局",
    "samr": "市场监管总局", "sasac": "国资委", "sdb": "证监会债券部",
    "stats": "统计局", "cn": "中国政府网", "immiau": "移民管理局",
    "zhengce": "国务院", "general": "通用",
}

# 省级映射
PROVINCE = {
    "ah": "安徽", "chongqing": "重庆", "guizhou": "贵州", "hainan": "海南",
    "hebei": "河北", "hunan": "湖南", "jiangsu": "江苏", "shaanxi": "陕西",
    "sh": "上海", "sichuan": "四川", "tianjin": "天津", "zhejiang": "浙江",
    "zj": "浙江",  # alias
    "shenzhen": "深圳",  # 副省级,单独算市级
    "beijing": "北京",  # 直辖市
    "gz": "广州",  # 省会
    "hangzhou": "杭州", "jinan": "济南", "suzhou": "苏州",
    "wuhan": "武汉", "taiyuan": "太原", "pudong": "上海(浦东)",
    "dianbai": "广东(电白)", "gaozhou": "广东(高州)", "huazhou": "广东(化州)",
    "huizhou": "广东(惠州)", "maoming": "广东(茂名)", "maonan": "广东(茂南)",
    "xinyi": "广东(信宜)", "xuzhou": "江苏(徐州)", "hunan": "湖南",
}

# 文件级 category 判定(top → 类别)
def classify_category(file_top: str) -> str:
    if file_top in NATIONAL_DEPT:
        return "国家级"
    # 省级(直辖市/省)
    direct_provinces = {"ah", "chongqing", "guizhou", "hainan", "hebei", "hunan", "jiangsu",
                        "shaanxi", "sh", "sichuan", "tianjin", "zhejiang", "zj", "beijing",
                        "fj", "gd", "hb", "hlj", "hn", "jl", "jx", "ln", "nmg", "nx",
                        "qh", "sc", "sd", "sx", "tj", "xj", "yn", "zj", "hk", "mo", "tw"}
    if file_top in direct_provinces:
        return "省级"
    # 其余(广东下面的地级市)算市级
    return "市级"


# 文件级 region 提取(国家级 → "全国",避免英文出现在 region 列)
def extract_region(file_top: str) -> str:
    if file_top in NATIONAL_DEPT:
        return "全国"
    return PROVINCE.get(file_top, file_top)


# 文件级 department 提取
def extract_department(file_top: str) -> str:
    if file_top in NATIONAL_DEPT:
        return NATIONAL_DEPT[file_top]
    return f"{PROVINCE.get(file_top, file_top)}政府"


# 简化路由:把 path 里的 :param 去掉,只剩 example 的实际 URL
def materialize_example(example: str) -> str:
    return example  # 已经是 example URL,直接用


def gen_source_id(file_path: str, example: str) -> str:
    """从 example 提取稳定 ID。"""
    # /gov/ah/kjt → rss_ah_kjt
    parts = [p for p in example.split("/") if p and p != "gov"]
    return "rss_" + "_".join(parts)[:60].replace(":", "_").replace("{", "_").replace("}", "_").replace(",", "_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="seed 后跑连通性探测")
    args = parser.parse_args()

    paths_file = Path("/app/python/scripts/rsshub_gov_paths.json")
    if not paths_file.exists():
        # 本地开发 fallback
        paths_file = Path("python/scripts/rsshub_gov_paths.json")
    if not paths_file.exists():
        paths_file = Path("rsshub_gov_paths.json")
    if not paths_file.exists():
        print("ERROR: 找不到 rsshub_gov_paths.json", file=sys.stderr)
        sys.exit(1)

    data = json.loads(paths_file.read_text(encoding="utf-8"))
    has_example = [r for r in data if r.get("example")]

    # 容器内 /app/data/ 存在 → 用容器路径;否则用本地相对路径
    _is_container = Path("/app/data").exists() and Path("/app/python").exists()
    DB_PATH = "/app/data/policy_radar.db" if _is_container else "data/policy_radar.db"
    RSS_BASE = "http://policy-radar-rsshub:1200"
    SPIDERS_DIR = Path("/app/python/crawlers/spiders") if _is_container else Path("python/crawlers/spiders")
    SPIDERS_DIR.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(DB_PATH)
    insert_count = skip_count = spider_count = 0

    for r in has_example:
        file_path = r["file"]  # e.g. "ah/kjt.ts" or "beijing/jw/tzgg.ts"
        example = r["example"]  # e.g. "/gov/ah/kjt"
        file_top = file_path.split("/")[0]
        # 文件中段(部门/子目录)
        file_mid = "/".join(file_path.split("/")[1:]).replace(".ts", "")

        sid = gen_source_id(file_path, example)
        # 防止 file_path 里包含下划线导致 sid 过长,简化
        sid = sid.replace("__", "_")

        url = RSS_BASE + example
        category = classify_category(file_top)
        region = extract_region(file_top)
        department = extract_department(file_top)
        # 委办前缀(对于 ah/kjt 这种,加一个"安徽省XX厅"的标识)
        if file_mid and file_mid not in ("namespace", "index"):
            if category == "国家级":
                # 国家级不加子部门,保持现有 name
                name = f"{department} {file_mid}"
            elif category == "省级":
                name = f"{region}省 {file_mid}"
            else:
                name = f"{region} {file_mid}"
        else:
            name = f"{department} RSS"

        # 1) DB
        existing = c.execute(
            "SELECT id FROM policy_sources WHERE source_id = ?", (sid,)
        ).fetchone()
        if existing:
            skip_count += 1
        else:
            c.execute(
                """INSERT INTO policy_sources
                   (source_id, name, url, category, region, department,
                    spider_config, frequency, enabled, last_status, created_at, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'daily', 0, 'pending', ?, ?)""",
                (sid, name, url, category, region, department,
                 json.dumps({"mode": "rss", "rss_path": example,
                             "file_path": file_path}, ensure_ascii=False),
                 __import__("datetime").datetime.utcnow().isoformat(),
                 json.dumps([category, region, department], ensure_ascii=False)),
            )
            insert_count += 1
            print(f"  + {sid:50s} {name}")

        # 2) spider.json
        spider_path = SPIDERS_DIR / f"{sid}.json"
        if not spider_path.exists():
            spider = {
                "source_id": sid,
                "name": name,
                "category": category,
                "region": region,
                "department": department,
                "list_url": url,
                "mode": "rss",
                "render_js": False,
                "frequency": "daily",
                "request_interval_min": 3,
                "request_interval_max": 6,
                "max_pages": 1,
                "notes": f"RSSHub {example} (服务端 RSSHub,RSS mode)",
            }
            spider_path.write_text(
                json.dumps(spider, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            spider_count += 1

    c.commit()
    c.close()
    print(f"\nSeed 完成: DB 新增 {insert_count} / 跳过 {skip_count} / spider 新增 {spider_count}")

    if args.probe:
        print("\n--- 探测连通性 ---")
        import asyncio
        import httpx

        async def probe_one(sid: str) -> tuple[str, bool, int]:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.get(RSS_BASE + example)
                    return sid, r.status_code == 200, r.status_code
            except Exception as e:
                return sid, False, 0

        async def run_probes():
            c2 = sqlite3.connect(DB_PATH)
            rows = c2.execute(
                "SELECT source_id, url FROM policy_sources WHERE source_id LIKE 'rss_%' AND enabled = 0"
            ).fetchall()
            print(f"待探测: {len(rows)}")
            ok = 0
            for sid, url in rows:
                example = url.replace(RSS_BASE, "")
                _, success, code = await probe_one(sid)
                status = "ok" if success else "failed"
                c2.execute(
                    "UPDATE policy_sources SET last_status = ? WHERE source_id = ?",
                    (status, sid),
                )
                if success:
                    ok += 1
                else:
                    print(f"  ✗ {sid}: HTTP {code}")
            c2.commit()
            c2.close()
            print(f"\n探测完成: {ok}/{len(rows)} 通过")

        asyncio.run(run_probes())


if __name__ == "__main__":
    main()
