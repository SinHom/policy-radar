"""批量创建国家级部门政策信源配置。

从已知模式创建 spider config JSON，推送到服务器后通过 crawl 验证。
跳过大港已有且正常产出的（nat_most, nat_mof），只创建缺失的。
"""

import json, os

SPIDERS_DIR = os.path.join(os.path.dirname(__file__), "..", "crawlers", "spiders")

NATIONAL_SOURCES = [
    {
        "source_id": "nat_ndrc",
        "name": "国家发改委",
        "category": "国家级",
        "region": "全国",
        "department": "发改委",
        "list_url": "https://www.ndrc.gov.cn/xxgk/zcfb/tz/",
        "list_selectors": {
            "item": ".u-list li, ul li a[href*='/xxgk/zcfb/tz/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span.date::text, .time::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .title",
            "content": ".TRS_Editor, .article-content, .content, .article_con",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_moe",
        "name": "教育部",
        "category": "国家级",
        "region": "全国",
        "department": "教育部",
        "list_url": "https://www.moe.gov.cn/jyb_xxgk/moe_1777/moe_307/",
        "list_selectors": {
            "item": ".moe_list li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, #artibodyTitle, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_mohrss",
        "name": "人社部",
        "category": "国家级",
        "region": "全国",
        "department": "人社部",
        "list_url": "https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/zcfg/",
        "list_selectors": {
            "item": ".news_list li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text, .time::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_nhc",
        "name": "国家卫健委",
        "category": "国家级",
        "region": "全国",
        "department": "卫健委",
        "list_url": "http://www.nhc.gov.cn/wjw/",
        "list_selectors": {
            "item": ".list li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text, .date::text"
        },
        "detail_selectors": {
            "title": "h1, .tit, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .con",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_mca",
        "name": "民政部",
        "category": "国家级",
        "region": "全国",
        "department": "民政部",
        "list_url": "https://www.mca.gov.cn/n152/n165/",
        "list_selectors": {
            "item": ".list_tit ul li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_mohurd",
        "name": "住建部",
        "category": "国家级",
        "region": "全国",
        "department": "住建部",
        "list_url": "https://www.mohurd.gov.cn/zhengce/zhengcewenjian/",
        "list_selectors": {
            "item": ".list li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text, .time::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .con",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_mofcom",
        "name": "商务部",
        "category": "国家级",
        "region": "全国",
        "department": "商务部",
        "list_url": "http://www.mofcom.gov.cn/article/b/",
        "list_selectors": {
            "item": ".listBox li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .con",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_mwr",
        "name": "水利部",
        "category": "国家级",
        "region": "全国",
        "department": "水利部",
        "list_url": "http://www.mwr.gov.cn/zwgk/zcfg/",
        "list_selectors": {
            "item": ".list li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .con",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_mot",
        "name": "交通运输部",
        "category": "国家级",
        "region": "全国",
        "department": "交通运输部",
        "list_url": "https://www.mot.gov.cn/zhengce/",
        "list_selectors": {
            "item": ".list li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text, .date::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .con",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    {
        "source_id": "nat_mee",
        "name": "生态环境部",
        "category": "国家级",
        "region": "全国",
        "department": "生态环境部",
        "list_url": "https://www.mee.gov.cn/xxgk2018/",
        "list_selectors": {
            "item": ".list li, ul li",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .con",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
]


def main():
    created = 0
    skipped = 0
    for src in NATIONAL_SOURCES:
        fname = f"{src['source_id']}.json"
        fpath = os.path.join(SPIDERS_DIR, fname)
        if os.path.exists(fpath):
            print(f"SKIP {fname} (已存在)")
            skipped += 1
            continue
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(src, f, ensure_ascii=False, indent=2)
        created += 1
        print(f"CREATE {fname} -> {src['name']}")

    print(f"\n创建 {created} 个，跳过 {skipped} 个")


if __name__ == "__main__":
    main()
