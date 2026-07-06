#!/usr/bin/env python3
"""批量生成河北省部门 spider 配置 JSON。"""
import json
from pathlib import Path

SPIDERS_DIR = Path(__file__).resolve().parent.parent / "crawlers" / "spiders"

# Default detail selectors (work for 90% of Chinese gov sites)
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

# ── 全部河北省级部门（含域名变更+需要 Playwright 的）──
SITES = [
    # === 省政府门户（聚合源）===
    ("prov_hebei_gov", "河北省政府·政策文件", "河北省人民政府",
     "https://www.hebei.gov.cn/columns/49f13cc2-db03-4d0c-b4fe-2f3f659d3b6e/index.html",
     {"item": "table tr", "title": "td a::text", "href": "td a::attr(href)", "date": "td:last-child::text"},
     False, 3, "省政府文件(政府令/冀政字/冀政办字),20条/页"),

    # === 核心经济部门 ===
    ("prov_hebei_fgw", "河北省发改委", "发改委",
     "https://hbdrc.hebei.gov.cn/xxgk_2232/fdzdgknr/zhzw/tztg_1120/index.html",
     {"item": "ul li", "title": "a::text", "href": "a::attr(href)", "date": "li::text"},
     False, 3, "发改委通知通告(域名hbdrc非fgw),tYYYYMMDD_NNNNNN.html"),

    ("prov_hebei_kjt", "河北省科技厅", "科技厅",
     "https://kjt.hebei.gov.cn/hebkjt/ztzllb/cxyycjfb/289019/index.html",
     DEFAULT_LIST, False, 2, "科技厅创新应用场景栏目(有平行栏目可配多个源)"),

    ("prov_hebei_czt", "河北省财政厅", "财政厅",
     "https://czt.hebei.gov.cn/xwdt/tzgg/",
     {"item": "ul li", "title": "a::attr(title)", "href": "a::attr(href)", "date": "li::text"},
     False, 3, "财政厅通知公告(已有RSSHub路由czt/xwdt辅助)"),

    ("prov_hebei_swt", "河北省商务厅", "商务厅",
     "http://swt.hebei.gov.cn/nx_html/tzwg/",
     DEFAULT_LIST, True, 2, "商务厅(httpx被墙,需Playwright)"),

    ("prov_hebei_sthjt", "河北省生态环境厅", "生态环境厅",
     "https://hbepb.hebei.gov.cn/hbhjt/zwgk/fdzdgknr/tongzhigonggao/index.html",
     {"item": "ul li, table tr", "title": "a::text", "href": "a::attr(href)", "date": "span::text"},
     False, 3, "生态环境厅(zycms CMS,24页)"),

    ("prov_hebei_zrzy", "河北省自然资源厅", "自然资源厅",
     "https://zrzy.hebei.gov.cn/heb/gongk/gkml/gggs/tz/",
     DEFAULT_LIST, False, 3, "自然资源厅通知公告"),

    ("prov_hebei_zfcxjst", "河北省住建厅", "住建厅",
     "https://zfcxjst.hebei.gov.cn/hbzjt/zcwj/gggs/index.html",
     DEFAULT_LIST, True, 2, "住建厅(httpx 412,需Playwright)"),

    ("prov_hebei_jtt", "河北省交通运输厅", "交通运输厅",
     "https://jtt.hebei.gov.cn/jtyst/zwgk/jcxxgk/zcwj/gfxwj/index.html",
     DEFAULT_LIST, False, 3, "交通厅省厅文件(130页,数据量大)"),

    ("prov_hebei_slt", "河北省水利厅", "水利厅",
     "http://slt.hebei.gov.cn/a/ZX/tzgg/",
     DEFAULT_LIST, False, 2, "水利厅(http, https自签证书)"),

    ("prov_hebei_whly", "河北省文旅厅", "文旅厅",
     "https://whly.hebei.gov.cn/xwzx/tzgg/",
     {"item": "ul li", "title": "a::text", "href": "a::attr(href)", "date": "span.date::text"},
     False, 2, "文旅厅(1189条记录,/c/YYYY-MM-DD/ID.html)"),

    # === 社会民生部门 ===
    ("prov_hebei_rst", "河北省人社厅", "人社厅",
     "https://rst.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "人社厅(SPA,纯JS渲染,必须Playwright)"),

    ("prov_hebei_wsjkw", "河北省卫健委", "卫健委",
     "https://wsjkw.hebei.gov.cn/tzgg/",
     DEFAULT_LIST, True, 2, "卫健委(httpx 403,需Playwright,.jhtml)"),

    ("prov_hebei_ylbzj", "河北省医保局", "医保局",
     "https://ylbzj.hebei.gov.cn/category/101",
     DEFAULT_LIST, False, 2, "医保局政府信息公开"),

    ("prov_hebei_tyjr", "河北省退役军人事务厅", "退役军人事务厅",
     "https://tyjrswt.hebei.gov.cn/gk/zfxxgkml/tzgg/",
     DEFAULT_LIST, False, 2, "退役军人厅(.shtml)"),

    ("prov_hebei_jyt", "河北省教育厅", "教育厅",
     "http://jyt.hebei.gov.cn/",
     DEFAULT_LIST, True, 2, "教育厅(需验证列表页URL)"),

    ("prov_hebei_minzheng", "河北省民政厅", "民政厅",
     "http://minzheng.hebei.gov.cn/",
     DEFAULT_LIST, True, 2, "民政厅(需验证列表页URL)"),

    ("prov_hebei_sft", "河北省司法厅", "司法厅",
     "http://sft.hebei.gov.cn/",
     DEFAULT_LIST, True, 2, "司法厅(需验证列表页URL)"),

    ("prov_hebei_gat", "河北省公安厅", "公安厅",
     "http://gat.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "公安厅(需验证列表页URL)"),

    ("prov_hebei_mw", "河北省民委", "民委",
     "http://mw.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "民族事务委员会(需验证列表页URL)"),

    # === 监管执法部门 ===
    ("prov_hebei_scjg", "河北省市监局", "市监局",
     "https://scjg.hebei.gov.cn/node/919",
     {"item": "a[href^=\"/info/\"]", "title": "a::text", "href": "a::attr(href)", "date": "a::text"},
     False, 3, "市监局(特殊结构:裸a标签,含知识产权局内容,1952条)"),

    ("prov_hebei_yjj", "河北省药监局", "药监局",
     "https://yjj.hebei.gov.cn/directory/web/hbpda/xxgk/zc/gfxwj/index.html",
     DEFAULT_LIST, False, 2, "药监局规范性文件"),

    ("prov_hebei_yjgl", "河北省应急管理厅", "应急管理厅",
     "https://yjgl.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "应急厅(Java portal,UUID型URL)"),

    ("prov_hebei_sjt", "河北省审计厅", "审计厅",
     "http://sjt.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "审计厅(需验证)"),

    # === 域名变更/特殊部门 ===
    ("prov_hebei_gzw", "河北省国资委", "国资委",
     "http://hbsa.hebei.gov.cn/gg.html",
     DEFAULT_LIST, False, 1, "国资委(域名hbsa非gzw)"),

    ("prov_hebei_rta", "河北省广电局", "广电局",
     "http://rta.hebei.gov.cn/lists/3/0/32.html",
     DEFAULT_LIST, False, 1, "广电局(域名rta非gdj)"),

    ("prov_hebei_hebwb", "河北省外办", "外办",
     "https://hebwb.hebei.gov.cn/list/list_zx.jsp?classId=255",
     DEFAULT_LIST, False, 1, "外办(域名hebwb非swb,JSP)"),

    ("prov_hebei_lycy", "河北省林业草原局", "林业草原局",
     "http://lycy.hebei.gov.cn/list_news_241.html",
     DEFAULT_LIST, False, 1, "林业草原局(域名lycy非lcj)"),

    ("prov_hebei_lswz", "河北省粮食和物资储备局", "粮食局",
     "https://lswz.hebei.gov.cn/xxgk/xxgkml/ghzj/ghjh/index.html",
     DEFAULT_LIST, False, 1, "粮食局(域名lswz非lsj)"),

    ("prov_hebei_sgdb", "河北省国动办", "国动办",
     "https://sgdb.hebei.gov.cn/category/list.html?id=19",
     DEFAULT_LIST, False, 1, "国动办(域名sgdb非gdb)"),

    ("prov_hebei_swj_jg", "河北省机关事务管理局", "机关事务管理局",
     "https://swj.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "机关局(域名swj非jgswj,.shtml)"),

    ("prov_hebei_sport", "河北省体育局", "体育局",
     "http://sport.hebei.gov.cn/plus/list.php?tid=48",
     DEFAULT_LIST, False, 2, "体育局(PHP DedeCMS)"),

    ("prov_hebei_tjj", "河北省统计局", "统计局",
     "http://tjj.hebei.gov.cn/hetj/wjtg/",
     DEFAULT_LIST, False, 1, "统计局文件通告"),

    ("prov_hebei_szj", "河北省数据和政务服务局", "数据和政务服务局",
     "http://szj.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "数据和政务服务局(需验证)"),

    ("prov_hebei_yjs", "河北省政府研究室", "政府研究室",
     "https://yjs.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "政府研究室(需验证)"),

    ("prov_hebei_wenwu", "河北省文物局", "文物局",
     "http://wenwu.hebei.gov.cn/",
     DEFAULT_LIST, True, 1, "文物局(需验证)"),

    # === 能源局（挂发改委下）===
    ("prov_hebei_nyj", "河北省能源局(发改委)", "能源局",
     "https://hbdrc.hebei.gov.cn/xxgk_2232/zc/wgfxwj/",
     {"item": "ul li", "title": "a::text", "href": "a::attr(href)", "date": "li::text"},
     False, 2, "能源局无独立域名,挂发改委下抓规范性文件"),
]

def main():
    count = 0
    for (sid, name, dept, list_url, list_sel, render_js, max_pages, notes) in SITES:
        cfg = {
            "source_id": sid,
            "name": name,
            "category": "省级",
            "region": "河北",
            "department": dept,
            "list_url": list_url,
            "mode": "html",
            "render_js": render_js,
            "frequency": "daily",
            "request_interval_min": 3,
            "request_interval_max": 6,
            "max_pages": max_pages,
            "list_selectors": list_sel,
            "detail_selectors": DEFAULT_DETAIL,
            "notes": notes,
        }
        path = SPIDERS_DIR / f"{sid}.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  OK  {sid:30} {name}")
        count += 1
    print(f"\nCreated {count} spider configs")

if __name__ == "__main__":
    main()
