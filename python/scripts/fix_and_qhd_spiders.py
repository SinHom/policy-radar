#!/usr/bin/env python3
"""修复已知问题的 spider 配置 + 创建秦皇岛市级 spider。"""
import json
from pathlib import Path

SPIDERS_DIR = Path(__file__).resolve().parent.parent / "crawlers" / "spiders"

# ── 修复：https → http（SSL SNI 问题）──
FIXES = {
    "prov_hebei_zrzy": {"list_url": "http://zrzy.hebei.gov.cn/heb/gongk/gkml/gggs/tz/"},
    "prov_hebei_sthjt": {"list_url": "http://hbepb.hebei.gov.cn/hbhjt/zwgk/fdzdgknr/tongzhigonggao/index.html"},
    "prov_hebei_jtt": {"list_url": "http://jtt.hebei.gov.cn/jtyst/zwgk/jcxxgk/zcwj/gfxwj/index.html"},
    "prov_hebei_swt": {"render_js": True, "list_url": "http://swt.hebei.gov.cn/nx_html/tzwg/"},
    "prov_hebei_zfcxjst": {"render_js": True},
    "prov_hebei_wsjkw": {"render_js": True, "list_url": "http://wsjkw.hebei.gov.cn/tzgg/"},
}

for sid, updates in FIXES.items():
    path = SPIDERS_DIR / f"{sid}.json"
    if not path.exists():
        print(f"  SKIP {sid}: file not found")
        continue
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg.update(updates)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  FIX  {sid}: {updates}")

# ── 秦皇岛市级 spider ──
# 秦皇岛市各部门网站通常挂在 qhd.gov.cn 下，或用子域名
# 注意：qhd.gov.cn 封锁非中国大陆 IP，需从服务器抓取
QHD_DEPT_URLS = {
    # 秦皇岛市政府门户 - 聚合政策
    "city_qhd_gov": ("秦皇岛市政府", "秦皇岛市人民政府",
        "http://www.qhd.gov.cn/", True, ""),
    # 市级局（很多挂在 qhd.gov.cn 下）
    "city_qhd_fgw": ("秦皇岛市发改委", "发改委",
        "http://fgw.qhd.gov.cn/", True, ""),
    "city_qhd_gxj": ("秦皇岛市工信局", "工信局",
        "http://gxj.qhd.gov.cn/", True, ""),
    "city_qhd_kjj": ("秦皇岛市科技局", "科技局",
        "http://kjj.qhd.gov.cn/", True, ""),
    "city_qhd_czj": ("秦皇岛市财政局", "财政局",
        "http://czj.qhd.gov.cn/", True, ""),
    "city_qhd_rsj": ("秦皇岛市人社局", "人社局",
        "http://rsj.qhd.gov.cn/", True, ""),
    "city_qhd_swj": ("秦皇岛市商务局", "商务局",
        "http://swj.qhd.gov.cn/", True, ""),
    "city_qhd_zjj": ("秦皇岛市住建局", "住建局",
        "http://zjj.qhd.gov.cn/", True, ""),
    "city_qhd_sthjj": ("秦皇岛市生态环境局", "生态环境局",
        "http://sthjj.qhd.gov.cn/", True, ""),
    "city_qhd_zyghj": ("秦皇岛市自然资源局", "自然资源局",
        "http://zyghj.qhd.gov.cn/", True, "域名zyghj非zrzyj,静态HTML分页index_N.html"),
    "city_qhd_jtj": ("秦皇岛市交通局", "交通局",
        "http://jtj.qhd.gov.cn/", True, ""),
    "city_qhd_nyncj": ("秦皇岛市农业农村局", "农业农村局",
        "http://nyncj.qhd.gov.cn/", True, ""),
    "city_qhd_lywgj": ("秦皇岛市文旅局", "文旅局",
        "http://lywgj.qhd.gov.cn/", True, "域名lywgj非whlyj"),
    # 水务局(swj)和商务局(swj)域名冲突,水务局占swj.qhd.gov.cn
    "city_qhd_swj_water": ("秦皇岛市水务局", "水务局",
        "http://swj.qhd.gov.cn/", True, "使用details2路径"),
    "city_qhd_wjw": ("秦皇岛市卫健委", "卫健委",
        "http://wjw.qhd.gov.cn/", True, ""),
    "city_qhd_scjg": ("秦皇岛市市监局", "市监局",
        "http://scjg.qhd.gov.cn/", True, ""),
}

DEFAULT_DETAIL = {
    "title": "h1, .article-title, .bt, meta[name=\"ArticleTitle\"]",
    "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .TRS_PreAppend, .Custom_UnionStyle, .zw_content, article",
    "date": "meta[name=\"PubDate\"], .date, .info span, .pub-date, .article-date",
}

DEFAULT_LIST = {
    "item": "ul li",
    "title": "a::text",
    "href": "a::attr(href)",
    "date": "span::text",
}

count = 0
for sid, (name, dept, list_url, render_js, notes) in QHD_DEPT_URLS.items():
    cfg = {
        "source_id": sid,
        "name": name,
        "category": "市级",
        "region": "秦皇岛",
        "department": dept,
        "list_url": list_url,
        "mode": "html",
        "render_js": render_js,
        "frequency": "daily",
        "request_interval_min": 5,
        "request_interval_max": 10,
        "max_pages": 2,
        "list_selectors": DEFAULT_LIST,
        "detail_selectors": DEFAULT_DETAIL,
        "notes": f"秦皇岛市级·{dept}·需从服务器抓取(qhd.gov.cn封锁非大陆IP){' ' + notes if notes else ''}",
    }
    path = SPIDERS_DIR / f"{sid}.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  NEW  {sid}: {name}")
    count += 1

print(f"\nDone: {len(FIXES)} fixes, {count} new QHD spiders")
