"""一次性补全国 27 委办 + 31 省级 + 省会(占位源,等用户填 URL)。

策略:
- 已有 source_id 跳过(不重复)
- 国家级委办 27 条(国务院组成部门核心)
- 31 省级行政区(每省 1 个省政府门户 placeholder)
- 省会 + plan city + 直辖市 = 共 31 城(每市 1 个市政府门户)
  (河北 11 个地市政府已在 add_hebei_sources.py 里加过)
- 全部 enabled=0,last_status='pending',tag 含 'placeholder'
- 真实 URL 待用户编辑填入

跑法(容器内):
    docker exec policy-radar-app python /app/python/scripts/add_china_sources.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# ============== 27 个国家级委办(国务院组成部门核心) ==============
# 格式:(short_id, 显示名, 常用直站域名)
NATIONAL_DEPT_ALL = [
    # 国务院办公厅 + 组成部门 26
    ("gov_cn",          "中国政府网(国务院)",       "www.gov.cn"),
    ("mfa",             "外交部",                   "www.mfa.gov.cn"),
    ("ndrc",            "国家发改委",               "www.ndrc.gov.cn"),
    ("moe",             "教育部",                   "www.moe.gov.cn"),
    ("most",            "科技部",                   "www.most.gov.cn"),
    # ("miit",          工信部 已有 rss_miit_*)
    ("miit2",           "工信部(部机关)",           "www.miit.gov.cn"),
    # ("mof",           财政部 已有 rss_mof_*)
    ("mof2",            "财政部(部机关)",           "www.mof.gov.cn"),
    # ("mofcom",        商务部 已有 rss_mofcom_*)
    ("mofcom2",         "商务部(部机关)",           "www.mof.gov.cn"),
    # ("moa",           农业农村部 已有 rss_moa_*)
    ("moa2",            "农业农村部(部机关)",       "www.moa.gov.cn"),
    # ("mee",           生态环境部 已有 rss_mee_*)
    ("mee2",            "生态环境部(部机关)",       "www.mee.gov.cn"),
    # ("mem",           应急管理部 已有 rss_mem_*)
    ("mem2",            "应急管理部(部机关)",       "www.mem.gov.cn"),
    ("moj",             "司法部",                   "www.moj.gov.cn"),
    # ("pbc",           央行 已有 rss_pbc_*)
    ("pbc2",            "中国人民银行(总行)",       "www.pbc.gov.cn"),
    ("mohrss",          "人社部",                   "www.mohrss.gov.cn"),
    ("mgs",             "自然资源部",               "www.mnr.gov.cn"),
    ("mohurd",          "住建部",                   "www.mohurd.gov.cn"),
    ("mot",             "交通运输部",               "www.mot.gov.cn"),
    ("mwr",             "水利部",                   "www.mwr.gov.cn"),
    ("mct",             "文化和旅游部",             "www.mct.gov.cn"),
    ("nhc",             "国家卫健委",               "www.nhc.gov.cn"),
    # ("sasac",         国资委 已有 rss_sasac_*)
    ("sasac2",          "国资委(机关)",             "www.sasac.gov.cn"),
    # ("chinatax",      税务总局 已有 rss_chinatax_*)
    ("chinatax2",       "税务总局(总局)",           "www.chinatax.gov.cn"),
    # ("samr",          市场监管总局 已有 rss_samr_*)
    ("samr2",           "市场监管总局(总局)",       "www.samr.gov.cn"),
    # ("nrta",          广电总局 已有 rss_nrta_*)
    ("nrta2",           "广电总局(总局)",           "www.nrta.gov.cn"),
    # ("stats",         统计局 已有 rss_stats_*)
    ("stats2",          "国家统计局(总司)",         "www.stats.gov.cn"),
    # 国家粮食和物资储备局
    ("lswz2",           "粮食和物资储备局",         "www.lswz.gov.cn"),
    # 国家体育总局
    ("sport",           "国家体育总局",             "www.sport.gov.cn"),
    # 国家医疗保障局
    ("nhsa",            "国家医保局",               "www.nhsa.gov.cn"),
    # 国务院港澳办
    ("hkmo",            "国务院港澳办",             "www.hmo.gov.cn"),
    # 国家信访局
    ("xfj",             "国家信访局",               "www.gjxfj.gov.cn"),
    # 国家能源局
    # ("nea",          国家能源局 已有 rss_nea_*)
    ("nea2",            "国家能源局(局机关)",       "www.nea.gov.cn"),
    # 国家国防科工局
    ("sastind",         "国防科工局",               "www.sastind.gov.cn"),
    # 国家烟草专卖局
    ("tobacco",         "国家烟草专卖局",           "www.tobacco.gov.cn"),
    # 国家林草局
    # ("forestry",      林草局 已有 rss_forestry_*)
    ("forestry2",       "国家林草局(局机关)",       "www.forestry.gov.cn"),
    # 国家知识产权局(国内没 RSSHub 路由)
    ("cnipa",           "国家知识产权局",           "www.cnipa.gov.cn"),
    # 国家文物局
    ("ncha",            "国家文物局",               "www.ncha.gov.cn"),
    # 国家档案局
    ("saac",            "国家档案局",               "www.saac.gov.cn"),
    # 国家密码管理局
    ("oscca",           "国家密码管理局",           "www.oscca.gov.cn"),
    # 国家保密局
    ("scs",             "国家保密局",               "www.gjbmj.gov.cn"),
]

# ============== 31 个省级行政区 ==============
# 格式:(short_id, 显示名, 政府门户域名)
PROVINCES_FULL = [
    # 4 个直辖市
    ("bj",  "北京市",       "www.beijing.gov.cn"),
    ("tj",  "天津市",       "www.tj.gov.cn"),
    ("sh",  "上海市",       "www.shanghai.gov.cn"),
    ("cq",  "重庆市",       "www.cq.gov.cn"),
    # 23 个省
    ("he",  "河北省",       "www.hebei.gov.cn"),  # 已有 rss_hebei_czt_xwdt
    ("sx",  "山西省",       "www.shanxi.gov.cn"),
    ("ln",  "辽宁省",       "www.ln.gov.cn"),
    ("jl",  "吉林省",       "www.jl.gov.cn"),
    ("hlj", "黑龙江省",     "www.hlj.gov.cn"),
    ("js",  "江苏省",       "www.js.gov.cn"),
    ("zj",  "浙江省",       "www.zj.gov.cn"),  # 已有 rss_zj_*
    ("ah",  "安徽省",       "www.ah.gov.cn"),  # 已有 rss_ah_kjt
    ("fj",  "福建省",       "www.fujian.gov.cn"),
    ("jx",  "江西省",       "www.jiangxi.gov.cn"),
    ("sd",  "山东省",       "www.shandong.gov.cn"),
    ("hn",  "河南省",       "www.henan.gov.cn"),
    ("hb",  "湖北省",       "www.hubei.gov.cn"),
    ("hun", "湖南省",       "www.hunan.gov.cn"),  # 已有 rss_hunan_*
    ("gd",  "广东省",       "www.gd.gov.cn"),
    ("gx",  "广西",         "www.gxzf.gov.cn"),
    ("hnn", "海南省",       "www.hainan.gov.cn"),  # 已有 rss_hainan_*
    ("sc",  "四川省",       "www.sc.gov.cn"),
    ("gz",  "贵州省",       "www.guizhou.gov.cn"),  # 已有 rss_guizhou_*
    ("yn",  "云南省",       "www.yn.gov.cn"),
    ("xz",  "西藏",         "www.xizang.gov.cn"),
    ("sn",  "陕西省",       "www.shaanxi.gov.cn"),  # 已有 rss_shaanxi_*
    ("gs",  "甘肃省",       "www.gansu.gov.cn"),
    ("qh",  "青海省",       "www.qinghai.gov.cn"),
    ("nx",  "宁夏",         "www.nx.gov.cn"),
    ("xj",  "新疆",         "www.xinjiang.gov.cn"),
    # 4 个特别行政区
    ("hk",  "香港",         "www.gov.hk"),
    ("mo",  "澳门",         "www.gov.mo"),
    ("tw",  "台湾",         "www.ey.gov.tw"),
    # 5 个自治区
    ("nmg", "内蒙古",       "www.nmg.gov.cn"),
]

# ============== 省会 + plan city + 直辖市(共 36) ==============
# 已有河北 11 城,只补其他省的省会 + 4 直辖市 + 5 plan city
CAPITALS = [
    # 4 个直辖市(已有)
    # 5 个 plan city
    ("shenzhen", "深圳市",     "www.sz.gov.cn"),
    ("qingdao",  "青岛市",     "www.qingdao.gov.cn"),
    ("dalian",   "大连市",     "www.dl.gov.cn"),
    ("ningbo",   "宁波市",     "www.ningbo.gov.cn"),
    ("xiamen",   "厦门市",     "www.xm.gov.cn"),
    # 省会城市(河北 11 个已在 add_hebei_sources.py 里加过,这里不加)
    ("taiyuan",  "太原市",     "www.taiyuan.gov.cn"),
    ("shenyang", "沈阳市",     "www.shenyang.gov.cn"),
    ("changchun","长春市",     "www.changchun.gov.cn"),
    ("haerbin",  "哈尔滨市",   "www.harbin.gov.cn"),
    ("nanjing",  "南京市",     "www.nanjing.gov.cn"),
    ("hangzhou", "杭州市",     "www.hangzhou.gov.cn"),
    ("hefei",    "合肥市",     "www.hefei.gov.cn"),
    ("fuzhou",   "福州市",     "www.fuzhou.gov.cn"),
    ("nanchang", "南昌市",     "www.nanchang.gov.cn"),
    ("jinan",    "济南市",     "www.jinan.gov.cn"),  # 已有 rss_jinan_*
    ("zhengzhou","郑州市",     "www.zhengzhou.gov.cn"),
    ("wuhan",    "武汉市",     "www.wuhan.gov.cn"),  # 已有 rss_wuhan_*
    ("changsha", "长沙市",     "www.changsha.gov.cn"),
    ("guangzhou","广州市",     "www.gz.gov.cn"),  # 已有 rss_gz_*
    ("haikou",   "海口市",     "www.haikou.gov.cn"),
    ("chengdu",  "成都市",     "www.chengdu.gov.cn"),
    ("guiyang",  "贵阳市",     "www.guiyang.gov.cn"),
    ("kunming",  "昆明市",     "www.km.gov.cn"),
    ("lasa",     "拉萨市",     "www.lasa.gov.cn"),
    ("xian",     "西安市",     "www.xa.gov.cn"),
    ("lanzhou",  "兰州市",     "www.lanzhou.gov.cn"),
    ("xining",   "西宁市",     "www.xining.gov.cn"),
    ("yinchuan", "银川市",     "www.yinchuan.gov.cn"),
    ("wulumuqi", "乌鲁木齐市", "www.urumqi.gov.cn"),
    ("huhehaote","呼和浩特市", "www.hhht.gov.cn"),
    ("nanning",  "南宁市",     "www.nanning.gov.cn"),
]


def main() -> None:
    _is_container = Path("/app/data").exists() and Path("/app/python").exists()
    db_path = "/app/data/policy_radar.db" if _is_container else "data/policy_radar.db"
    spiders_dir = Path("/app/python/crawlers/spiders") if _is_container else Path("python/crawlers/spiders")
    spiders_dir.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(db_path)
    now = __import__("datetime").datetime.utcnow().isoformat()
    inserted = skipped = spider_new = 0

    # 国家级委办
    print("=== 国家级委办 ===")
    for short_id, name, domain in NATIONAL_DEPT_ALL:
        sid = f"cn_{short_id}"
        url = f"https://{domain}/zwgk"
        existing = c.execute("SELECT id FROM policy_sources WHERE source_id = ?", (sid,)).fetchone()
        if existing:
            skipped += 1
            print(f"  skip {sid:25s} {name}")
            continue
        c.execute(
            """INSERT INTO policy_sources
               (source_id, name, url, category, region, department,
                spider_config, frequency, enabled, last_status, created_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'daily', 0, 'pending', ?, ?)""",
            (sid, name, url, "国家级", "全国", name,
             json.dumps({"mode": "playwright", "list_url": url,
                         "notes": f"{name}占位源,需要编辑 URL + CSS 选择器",
                         "placeholder": True}, ensure_ascii=False),
             now, json.dumps(["国家级", "全国", name, "placeholder"], ensure_ascii=False)),
        )
        spider_path = spiders_dir / f"{sid}.json"
        if not spider_path.exists():
            spider_path.write_text(json.dumps({
                "source_id": sid, "name": name, "category": "国家级",
                "region": "全国", "department": name, "list_url": url,
                "mode": "playwright", "render_js": True, "frequency": "daily",
                "request_interval_min": 5, "request_interval_max": 10, "max_pages": 1,
                "notes": f"{name}占位源,需要编辑 URL + CSS 选择器",
                "placeholder": True,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            spider_new += 1
        inserted += 1
        print(f"  + {sid:25s} {name}")

    # 31 省级
    print("\n=== 31 省级行政区 ===")
    for short_id, name, domain in PROVINCES_FULL:
        sid = f"pr_{short_id}"
        url = f"https://{domain}/zwgk"
        existing = c.execute("SELECT id FROM policy_sources WHERE source_id = ?", (sid,)).fetchone()
        if existing:
            skipped += 1
            print(f"  skip {sid:25s} {name}")
            continue
        # region:去掉"省/市"后缀,用于筛选
        region_short = name
        for suffix in ("省", "市", "自治区"):
            if region_short.endswith(suffix):
                region_short = region_short[:-len(suffix)]
                break
        full_dept = f"{name}政府"
        c.execute(
            """INSERT INTO policy_sources
               (source_id, name, url, category, region, department,
                spider_config, frequency, enabled, last_status, created_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'daily', 0, 'pending', ?, ?)""",
            (sid, f"{name}政府门户", url, "省级", region_short, full_dept,
             json.dumps({"mode": "playwright", "list_url": url,
                         "notes": f"{name}政府门户占位源,需要编辑 URL + CSS 选择器",
                         "placeholder": True}, ensure_ascii=False),
             now, json.dumps(["省级", region_short, full_dept, "placeholder"], ensure_ascii=False)),
        )
        spider_path = spiders_dir / f"{sid}.json"
        if not spider_path.exists():
            spider_path.write_text(json.dumps({
                "source_id": sid, "name": f"{name}政府门户", "category": "省级",
                "region": region_short, "department": full_dept, "list_url": url,
                "mode": "playwright", "render_js": True, "frequency": "daily",
                "request_interval_min": 5, "request_interval_max": 10, "max_pages": 1,
                "notes": f"{name}政府门户占位源,需要编辑 URL + CSS 选择器",
                "placeholder": True,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            spider_new += 1
        inserted += 1
        print(f"  + {sid:25s} {name}政府门户")

    # 省会 + plan city
    print("\n=== 省会 + plan city ===")
    for short_id, name, domain in CAPITALS:
        sid = f"cap_{short_id}"
        url = f"https://{domain}/zwgk"
        existing = c.execute("SELECT id FROM policy_sources WHERE source_id = ?", (sid,)).fetchone()
        if existing:
            skipped += 1
            print(f"  skip {sid:25s} {name}")
            continue
        # city name 已经含 "市"(如 "深圳市"),不要再加 "市" 前缀
        full_dept = f"{name}政府"  # "深圳市政府"
        # region 字段去掉 "市" 后缀(用于筛选)
        region_short = name[:-1] if name.endswith("市") else name
        # name 也用 "深圳市政府门户" 但不要重复"市"
        display_name = f"{name}政府门户"
        c.execute(
            """INSERT INTO policy_sources
               (source_id, name, url, category, region, department,
                spider_config, frequency, enabled, last_status, created_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'daily', 0, 'pending', ?, ?)""",
            (sid, display_name, url, "市级", region_short, full_dept,
             json.dumps({"mode": "playwright", "list_url": url,
                         "notes": f"{name}政府门户占位源,需要编辑 URL + CSS 选择器",
                         "placeholder": True}, ensure_ascii=False),
             now, json.dumps(["市级", region_short, full_dept, "placeholder"], ensure_ascii=False)),
        )
        spider_path = spiders_dir / f"{sid}.json"
        if not spider_path.exists():
            spider_path.write_text(json.dumps({
                "source_id": sid, "name": display_name, "category": "市级",
                "region": region_short, "department": full_dept, "list_url": url,
                "mode": "playwright", "render_js": True, "frequency": "daily",
                "request_interval_min": 5, "request_interval_max": 10, "max_pages": 1,
                "notes": f"{name}政府门户占位源,需要编辑 URL + CSS 选择器",
                "placeholder": True,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            spider_new += 1
        inserted += 1
        print(f"  + {sid:25s} {display_name}")

    c.commit()
    c.close()
    print(f"\n汇总: DB 新增 {inserted} / 跳过 {skipped} / spider 新建 {spider_new}")


if __name__ == "__main__":
    main()