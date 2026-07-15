"""批量创建/修复河北省和秦皇岛市委办局信源配置。

修复策略：
- QHD 部门用 a[href*='/home/details'] 精确匹配政策详情页
- 河北省级部门用部门专属 URL 模式
"""

import json, os

SPIDERS_DIR = os.path.join(os.path.dirname(__file__), "..", "crawlers", "spiders")

# 新信源 + 需要修复的信源
SOURCES = [
    # === 河北省新增 ===
    {
        "source_id": "prov_hebei_sthjt",
        "name": "河北省生态环境厅",
        "category": "省级",
        "region": "河北",
        "department": "生态环境厅",
        "list_url": "https://hbepb.hebei.gov.cn/hbhjt/zwgk/fdzdgknr/tongzhigonggao/",
        "list_selectors": {
            "item": "a[href*='/hbhjt/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, meta[name=\"ArticleTitle\"]",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .Custom_UnionStyle",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 2,
    },
    {
        "source_id": "prov_hebei_slt",
        "name": "河北省水利厅",
        "category": "省级",
        "region": "河北",
        "department": "水利厅",
        "list_url": "http://slt.hebei.gov.cn/a/zc/",
        "list_selectors": {
            "item": "a[href*='/a/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, meta[name=\"ArticleTitle\"]",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 2,
    },
    {
        "source_id": "prov_hebei_swt",
        "name": "河北省商务厅",
        "category": "省级",
        "region": "河北",
        "department": "商务厅",
        "list_url": "http://swt.hebei.gov.cn/newsContentform/infoPublicList?channelId=621&y=1",
        "list_selectors": {
            "item": "a[href*='/nx_html/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 2,
    },
    # === 秦皇岛市修复（精确选择器） ===
    {
        "source_id": "city_qhd_fgw",
        "name": "秦皇岛市发改委",
        "category": "市级",
        "region": "秦皇岛",
        "department": "发改委",
        "list_url": "http://fgw.qhd.gov.cn/home/list/?code=Njc2MTAyMjc0NzM2&pcode=MDE3NTkzNDM3MjA2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "city_qhd_gxj",
        "name": "秦皇岛市工信局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "工信局",
        "list_url": "http://gxj.qhd.gov.cn/home/list/?code=NzU5&pcode=MDE3NjMxOTgyNTE2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "city_qhd_zjj",
        "name": "秦皇岛市住建局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "住建局",
        "list_url": "http://zjj.qhd.gov.cn/home/xzzfgstablist?code=NTM5&pcode=NTc2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "city_qhd_swj",
        "name": "秦皇岛市商务局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "商务局",
        "list_url": "http://swj.qhd.gov.cn/home/list/?code=NjMx&pcode=MDE3NjMxOTgyNTE2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "city_qhd_kjj",
        "name": "秦皇岛市科技局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "科技局",
        "list_url": "http://kjj.qhd.gov.cn/home/list/?code=NjA5&pcode=MDE3NjMxOTgyNTE2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "city_qhd_nyncj",
        "name": "秦皇岛市农业农村局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "农业农村局",
        "list_url": "http://nyncj.qhd.gov.cn/home/list/?code=MTA1&pcode=MDE3NjMxOTgyNTE2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    # === 秦皇岛市新增 ===
    {
        "source_id": "city_qhd_czj",
        "name": "秦皇岛市财政局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "财政局",
        "list_url": "http://czj.qhd.gov.cn/home/list/?code=NTk5&pcode=MDE3NjMxOTgyNTE2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "city_qhd_scjg",
        "name": "秦皇岛市市监局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "市监局",
        "list_url": "http://scjg.qhd.gov.cn/home/list/?code=NjE1&pcode=MDE3NjMxOTgyNTE2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "city_qhd_sthjj",
        "name": "秦皇岛市生态环境局",
        "category": "市级",
        "region": "秦皇岛",
        "department": "生态环境局",
        "list_url": "http://sthjj.qhd.gov.cn/home/list/?code=NjA2&pcode=MDE3NjMxOTgyNTE2",
        "list_selectors": {
            "item": "a[href*='/home/details']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date, .info span"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
]


def main():
    created = 0
    updated = 0
    for src in SOURCES:
        fname = f"{src['source_id']}.json"
        fpath = os.path.join(SPIDERS_DIR, fname)
        action = "UPDATE" if os.path.exists(fpath) else "CREATE"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(src, f, ensure_ascii=False, indent=2)
        if action == "CREATE":
            created += 1
        else:
            updated += 1
        print(f"{action} {fname} -> {src['name']}")

    print(f"\n创建 {created} 个，更新 {updated} 个")


if __name__ == "__main__":
    main()
