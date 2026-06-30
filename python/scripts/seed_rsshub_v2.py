"""Seed RSSHub gov/* 路由 → policy_sources 表(基于 rsshub_gov_paths.json)。

改进(v3):
- SUFFIX_MAP 把 ah/kjt 翻译为「安徽省-科技厅」(而非「安徽政府」)
- --probe 并发探测真实可达性,失败的标 disabled
- 加 chongqing/gzw + mfa/wjdt 两条无 example 的(给默认 category)

跑法(容器内):
    docker exec policy-radar-app python /app/python/scripts/seed_rsshub_v2.py
    docker exec policy-radar-app python /app/python/scripts/seed_rsshub_v2.py --probe
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

# ============== 国家级部委映射(file top → 中文部门名) ==============
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
    "zhengce": "国务院", "general": "通用", "caac": "民航局",
}

# ============== 省级映射(直辖市/省) ==============
PROVINCE_FULL = {
    "ah": "安徽省", "beijing": "北京市", "chongqing": "重庆市",
    "guizhou": "贵州省", "hainan": "海南省", "hebei": "河北省",
    "hunan": "湖南省", "jiangsu": "江苏省", "shaanxi": "陕西省",
    "sh": "上海市", "sichuan": "四川省", "tianjin": "天津市",
    "zhejiang": "浙江省", "zj": "浙江省",  # alias
}

# ============== 市级 ==============
CITY = {
    "shenzhen": "深圳市", "hangzhou": "杭州市", "jinan": "济南市",
    "suzhou": "苏州市", "wuhan": "武汉市", "taiyuan": "太原市",
    "pudong": "上海(浦东)", "gz": "广州市",
    # 广东下面的地级市/区县
    "dianbai": "广东(电白)", "gaozhou": "广东(高州)", "huazhou": "广东(化州)",
    "huizhou": "广东(惠州)", "maoming": "广东(茂名)", "maonan": "广东(茂南)",
    "xinyi": "广东(信宜)", "xuzhou": "江苏(徐州)",
}

# ============== 文件名后缀 → 部门名(各省通用) ==============
# 形如 aaa/fgw.ts → 「XX省-发改委」,aaa/sft.ts → 「XX省-司法厅」
SUFFIX_MAP = {
    # 中央部委通用(国家级也用同套)
    "fgw": "发改委", "gxj": "工信厅", "kjt": "科技厅", "kjj": "科技局",
    "sft": "司法厅", "sjw": "审计厅", "tjj": "统计局", "lyj": "林业局",
    "czt": "财政厅", "jyt": "教育厅", "wjw": "卫健委", "rsj": "人社厅",
    "hrss": "人社局", "swj": "商务厅", "gtj": "自然资源局", "slt": "水利厅",
    "nyt": "农业农村厅", "ysj": "药监局", "amr": "市场监管局",
    "yjglj": "应急管理局", "fxyj": "发改委(价格)",
    "gzw": "国资委", "gjj": "国资委",
    "hgswj": "海关", "fj": "反腐", "zwgk": "政务公开", "zcjd": "政策解读",
    "tzgg": "通知公告", "xwdt": "新闻动态", "zfxxgk": "政府信息公开",
    "zcwj": "政策文件", "zcgk": "政策法规", "zcfg": "政策法规",
    "rsks": "人事考试", "rsksy": "人事考试", "sydwgkzp": "事业单位",
    "fxrw": "风险人物", "gfgg": "规范公告", "gjhz": "国际合作",
    "hqsy": "后勤", "kjkx": "科技", "kpjy": "科普教育",
    "yzjz": "证监会要闻", "zhxw": "综合新闻", "dsj": "电视剧",
    "gzlw": "工作论文", "zcyj": "政策研究", "gss": "工交司",
    "news": "新闻", "bm": "部门",
    "yyzl": "医院管理", "wybsf": "物业", "ghs": "规划司",
    "kphd": "科普活动", "kjkxyjyyy": "科技研究",
    "jczyds": "基础研究", "zlxz": "资料下载", "rsj": "人社",
    "szlh": "立法", "szksy": "考试院", "xxgk": "信息公开",
    "zjj": "住建局", "zzb": "组织部", "whyw": "外事要闻",
    "iitb": "工信厅", "tjftz": "天津开发区", "tjrcgzw": "人才",
    "bphc": "保护处", "kw": "科委", "jw": "经委",
    "bjedu": "北京教育", "gh": "规划", "policy_anal": "政策分析",
    "s78": "规划司", "bond": "国债司", "gjs": "国际司",
    "szcpxx": "农产品质量安全", "zdscxx": "重大",
    "jiaotongyaowen": "交通要闻", "lfyjzj": "法律援助",
    "aac": "公证仲裁", "ywdt": "要闻", "fdzdgknr": "法定主动公开内容",
    "915": "消保", "xxgk_ggtg": "信息公开公告通告", "GB": "国标",
    "yaowenn": "要闻", "wxzw": "微信政务", "xxh": "宣传",
    "zfgb": "立法", "zj": "浙江", "zcjd": "政策解读",
    "gwy": "公务员", "fg": "法规", "doc": "公文", "yyw": "要闻",
    "goutongjiaoliu": "沟通交流", "tradeAnnouncement": "贸易公告",
    "trade-announcement": "贸易公告", "business": "业务",
    "complaint": "投诉", "auditstatus": "审计", "zfxxgk_zdgk": "主动公开",
    "news/index": "新闻", "xw": "新闻", "xwsj": "新闻事件",
    "tzgg": "通知公告", "yw": "要闻", "dgwj": "党工文件",
    "wcwk": "维权", "gggs": "公告公示", "dsj": "电视剧",
    "fw": "服务", "list": "列表", "paimai": "拍卖",
    "nnsa": "核安全", "sgcc": "煤矿安全", "rsj": "人社",
    "main": "主页", "bphc": "保护处",
    "zfcg-helper": "政府采购助手", "zfcg": "政府采购",
    "ningbogzw": "宁波国资委", "ningborsjnotice": "宁波人社",
    "search": "搜索", "notice": "通知", "sy": "首页",
    "tx": "通讯", "zlxz": "资料下载", "gfgz": "法规规章",
    "wjfb": "文件发布", "wjgs": "文件公示", "yjzj": "研究",
    "xcgj": "宣传", "zdxx": "重点", "gss": "工交司",
    "xfsf": "信访", "zffw": "政务服务", "policy": "政策",
    "anal": "分析", "gzlw": "工作论文", "zcyj": "政策研究",
}

# ============== Category 判定 ==============
def classify_category(file_top: str) -> str:
    if file_top in NATIONAL_DEPT:
        return "国家级"
    if file_top in PROVINCE_FULL:
        return "省级"
    return "市级"

# ============== Region 提取 ==============
def extract_region(file_top: str) -> str:
    if file_top in NATIONAL_DEPT:
        return "全国"
    if file_top in PROVINCE_FULL:
        return PROVINCE_FULL[file_top].replace("省", "").replace("市", "").replace("市", "")
    if file_top in CITY:
        # 去掉"市"后缀但保留括号注释(例:广东(电白) → 广东(电白))
        v = CITY[file_top]
        return v.rstrip("市") if v.endswith("市") and "(" not in v else v
    return file_top

# ============== Department 提取(改进版) ==============
def _match_suffix(token: str) -> str | None:
    """在 SUFFIX_MAP 里查 token,失败就按 '-' 拆再查。"""
    if token in SUFFIX_MAP:
        return SUFFIX_MAP[token]
    if "-" in token:
        head = token.split("-")[0]
        if head in SUFFIX_MAP:
            return SUFFIX_MAP[head]
    return None


def extract_department(file_top: str, file_mid: str) -> str:
    """从 file path 推断部门名。例 ah/kjt.ts → "安徽省-科技厅" """
    if file_top in NATIONAL_DEPT:
        return NATIONAL_DEPT[file_top]
    region_full = PROVINCE_FULL.get(file_top) or CITY.get(file_top) or file_top
    # file_mid 可能是 "kjt"、"hrss/szksy"、"rsj/gggs"、"ningbogzw-notice"
    mid_first = file_mid.split("/")[0] if file_mid else ""
    dept = _match_suffix(mid_first)
    if dept:
        return f"{region_full}-{dept}"
    return f"{region_full}-{file_mid or '综合'}"

# ============== Name 提取 ==============
def extract_name(file_top: str, file_mid: str, dept: str, category: str) -> str:
    """生成「区域-部门 栏目」名"""
    # 国家级:直接用「部门名 + 栏目」
    if category == "国家级":
        if file_mid and file_mid not in ("namespace", "index"):
            # 委办内栏目
            suffix = _match_suffix(file_mid.split("/")[0]) if file_mid else None
            if suffix and suffix != dept:
                return f"{dept}-{suffix}"
            return f"{dept} {file_mid}"
        return f"{dept} RSS"
    # 省级/市级:「省-X厅 + 栏目」
    if file_mid and file_mid not in ("namespace", "index"):
        return f"{dept} {file_mid}"
    return f"{dept} RSS"


def gen_source_id(file_path: str, example: str) -> str:
    parts = [p for p in example.split("/") if p and p != "gov"]
    return "rss_" + "_".join(parts)[:60].replace(":", "_").replace("{", "_").replace("}", "_").replace(",", "_").replace("&", "_").replace("=", "_").replace("?", "_")


# ============== 手动补充的 2 条无 example 路由 ==============
# chongqing/gzw → 重庆市国资委;example 用常见 category
# mfa/wjdt → 外交部;example 用外事动态
EXTRA_ROUTES = [
    {
        "file": "chongqing/gzw.ts",
        "path": "/gzw/:category{.+}?",
        "example": "/gov/chongqing/gzw/zcfg",
    },
    {
        "file": "mfa/wjdt.ts",
        "path": "/wjdt/:category?",
        "example": "/gov/mfa/wjdt/fyrbt",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="seed 后跑连通性探测(失败标 disabled)")
    parser.add_argument("--from-rsshub", action="store_true", help="从 RSSHub live API 拉路由(容器内推荐)")
    parser.add_argument("--rsshub-url", default="http://policy-radar-rsshub:1200", help="RSSHub base URL")
    parser.add_argument("--probe-concurrency", type=int, default=20)
    args = parser.parse_args()

    has_example = []
    if args.from_rsshub:
        import httpx
        try:
            r = httpx.get(f"{args.rsshub_url}/api/routes/public", timeout=30)
            r.raise_for_status()
            all_routes = r.json()
            import re
            for route in all_routes:
                path = route.get("path", "")
                if not path.startswith("/gov/") or not route.get("example"):
                    continue
                if re.search(r":\w+\{", path):
                    continue
                has_example.append({
                    "file": path.lstrip("/").replace("/", "_") + ".ts",
                    "path": path,
                    "example": route.get("example"),
                })
        except Exception as e:
            print(f"  RSSHub 拉路由失败: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        paths_file = Path("/app/python/scripts/rsshub_gov_paths.json")
        if not paths_file.exists():
            paths_file = Path("/app/rsshub_gov_paths.json")
        if not paths_file.exists():
            paths_file = Path("python/scripts/rsshub_gov_paths.json")
        if not paths_file.exists():
            paths_file = Path("rsshub_gov_paths.json")
        if not paths_file.exists():
            print("ERROR: 找不到 rsshub_gov_paths.json,试试 --from-rsshub", file=sys.stderr)
            sys.exit(1)
        data = json.loads(paths_file.read_text(encoding="utf-8"))
        has_example = [r for r in data if r.get("example")]
        # 手动补 2 条
        for extra in EXTRA_ROUTES:
            if extra not in has_example:
                has_example.append(extra)

    _is_container = Path("/app/data").exists() and Path("/app/python").exists()
    DB_PATH = "/app/data/policy_radar.db" if _is_container else "data/policy_radar.db"
    RSS_BASE = args.rsshub_url
    SPIDERS_DIR = Path("/app/python/crawlers/spiders") if _is_container else Path("python/crawlers/spiders")
    SPIDERS_DIR.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(DB_PATH)
    insert_count = skip_count = spider_count = update_count = 0

    # 先 update 已有源(让 region/department 更准)
    for r in has_example:
        file_path = r["file"]
        example = r["example"]
        file_top = file_path.split("/")[0]
        file_mid = "/".join(file_path.split("/")[1:]).replace(".ts", "")
        sid = gen_source_id(file_path, example)
        sid = sid.replace("__", "_").rstrip("_")

        category = classify_category(file_top)
        region = extract_region(file_top)
        department = extract_department(file_top, file_mid)
        name = extract_name(file_top, file_mid, department, category)
        url = RSS_BASE + example

        # 1) DB
        existing = c.execute(
            "SELECT id, name, region, department, category FROM policy_sources WHERE source_id = ?", (sid,)
        ).fetchone()
        if existing:
            # UPDATE name/region/department/category(更精准)
            cur_name, cur_region, cur_dept, cur_cat = existing[1], existing[2], existing[3], existing[4]
            if (cur_name != name or cur_region != region or cur_dept != department or cur_cat != category):
                c.execute(
                    "UPDATE policy_sources SET name=?, region=?, department=?, category=? WHERE source_id=?",
                    (name, region, department, category, sid),
                )
                update_count += 1
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
                "source_id": sid, "name": name, "category": category,
                "region": region, "department": department, "list_url": url,
                "mode": "rss", "render_js": False, "frequency": "daily",
                "request_interval_min": 3, "request_interval_max": 6, "max_pages": 1,
                "notes": f"RSSHub {example} (服务端 RSSHub,RSS mode)",
            }
            spider_path.write_text(
                json.dumps(spider, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            spider_count += 1

    c.commit()
    c.close()
    print(f"\nSeed 完成: DB 新增 {insert_count} / UPDATE {update_count} / 跳过 {skip_count} / spider 新增 {spider_count}")

    if args.probe:
        print("\n--- 探测连通性(并发 20) ---")
        import httpx

        async def probe_all():
            c2 = sqlite3.connect(DB_PATH)
            rows = c2.execute(
                "SELECT id, source_id, url FROM policy_sources WHERE source_id LIKE 'rss_%' AND enabled = 0"
            ).fetchall()
            print(f"待探测: {len(rows)}")
            sem = asyncio.Semaphore(args.probe_concurrency)

            async def one(row):
                _id, sid, url = row
                async with sem:
                    try:
                        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                            r = await client.get(url)
                            return sid, r.status_code == 200, r.status_code
                    except Exception as e:
                        return sid, False, str(e)[:50]

            results = await asyncio.gather(*[one(r) for r in rows])
            ok = fail = 0
            for sid, success, code in results:
                if success:
                    ok += 1
                    c2.execute(
                        "UPDATE policy_sources SET last_status = 'ok' WHERE source_id = ?", (sid,)
                    )
                else:
                    fail += 1
                    c2.execute(
                        "UPDATE policy_sources SET last_status = 'failed' WHERE source_id = ?", (sid,)
                    )
            c2.commit()
            c2.close()
            print(f"\n探测完成: {ok} OK / {fail} failed")
            if fail:
                print("\n失败清单(前 30):")
                failed = [r for r in results if not r[1]]
                for sid, _, code in failed[:30]:
                    print(f"  ✗ {sid:50s} {code}")
                if len(failed) > 30:
                    print(f"  ... 还有 {len(failed)-30}")

        asyncio.run(probe_all())


if __name__ == "__main__":
    main()
