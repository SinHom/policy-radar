"""根据《河北省网站.md》清单，批量创建缺失的河北省/秦皇岛市信源配置。

关键发现：
- 省发改委: hbdrc.hebei.gov.cn (非 ndrc.hebei.gov.cn)
- 省审计厅: www.hebaudit.gov.cn (非 sjt.hebei.gov.cn)
- 省教育厅: jyt.hebei.gov.cn
- 省公安厅: gat.hebei.gov.cn
- 省民政厅: minzheng.hebei.gov.cn
- 市财政局(信息公开): www.qhd.gov.cn:81/list.jsp
- 开发区: qetdz.gov.cn
- 等等
"""

import json, os

SPIDERS_DIR = os.path.join(os.path.dirname(__file__), "..", "crawlers", "spiders")

# 模板：省厅通用
def prov_config(sid, name, dept, list_url, extra_selectors=None):
    """生成省级委办局标准配置"""
    item_sel = extra_selectors.get("item", "a[href*='/']") if extra_selectors else "li a, .list a"
    title_sel = extra_selectors.get("title", "a::text") if extra_selectors else "a::text"
    href_sel = extra_selectors.get("href", "a::attr(href)") if extra_selectors else "a::attr(href)"

    return {
        "source_id": sid,
        "name": name,
        "category": "省级",
        "region": "河北",
        "department": dept,
        "list_url": list_url,
        "list_selectors": {
            "item": item_sel,
            "title": title_sel,
            "href": href_sel,
            "date": "span::text, .date::text, .time::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt, meta[name=\"ArticleTitle\"]",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content, .Custom_UnionStyle, .zw_content",
            "date": "meta[name=\"PubDate\"], .date, .info span, .time"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 2,
    }

# 模板：秦皇岛市局通用
def qhd_config(sid, name, dept, list_url):
    return {
        "source_id": sid,
        "name": name,
        "category": "市级",
        "region": "秦皇岛",
        "department": dept,
        "list_url": list_url,
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
    }


SOURCES = [
    # ============ 河北省新增/修正 ============
    # 省发改委 - 修正域名
    prov_config("prov_hebei_fgw2", "河北省发改委", "发改委",
                "http://hbdrc.hebei.gov.cn/ndjh_1231/"),
    # 省教育厅
    prov_config("prov_hebei_jyt", "河北省教育厅", "教育厅",
                "http://jyt.hebei.gov.cn/"),
    # 省公安厅
    prov_config("prov_hebei_gat", "河北省公安厅", "公安厅",
                "https://gat.hebei.gov.cn/"),
    # 省民政厅
    prov_config("prov_hebei_minzheng2", "河北省民政厅", "民政厅",
                "https://minzheng.hebei.gov.cn/"),
    # 省审计厅 - 特殊域名
    prov_config("prov_hebei_sjt2", "河北省审计厅", "审计厅",
                "https://www.hebaudit.gov.cn/"),
    # 省卫健委
    prov_config("prov_hebei_wsjkw", "河北省卫健委", "卫健委",
                "http://wsjkw.hebei.gov.cn/"),
    # 省自然资源厅 - 政策文件页
    prov_config("prov_hebei_zrzy2", "河北省自然资源厅", "自然资源厅",
                "https://zrzy.hebei.gov.cn/heb/gongk/gkml/zcwj/"),
    # 省住建厅 - 厅发文件
    prov_config("prov_hebei_zfcxjst", "河北省住建厅", "住建厅",
                "http://zfcxjst.hebei.gov.cn/hbzjt/zcwj/tfwj/"),
    # 省交通厅 - 修正
    prov_config("prov_hebei_jtt2", "河北省交通厅", "交通厅",
                "https://jtt.hebei.gov.cn/jtyst/zwgk/jcxxgk/xxgkzn/"),
    # 省税务局 - 国税系统域名
    prov_config("prov_hebei_tax", "河北省税务局", "税务局",
                "https://hebei.chinatax.gov.cn/"),
    # 省科技厅 - 修正
    prov_config("prov_hebei_kjt2", "河北省科技厅", "科技厅",
                "https://kjt.hebei.gov.cn/"),
    # 省委金融办
    prov_config("prov_hebei_jrb", "河北省金融办", "金融办",
                "https://www.hebswjrb.gov.cn/"),

    # ============ 秦皇岛市新增 ============
    # 市政府门户-政策文件
    {
        "source_id": "city_qhd_gov",
        "name": "秦皇岛市政府",
        "category": "市级",
        "region": "秦皇岛",
        "department": "市政府",
        "list_url": "http://www.qhd.gov.cn:81/list.jsp?deptid=58&code=277",
        "list_selectors": {
            "item": "a[href*='info/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "td::text"
        },
        "detail_selectors": {
            "title": "h1, .title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .content, .article-content",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    # 市规范性文件
    {
        "source_id": "city_qhd_gov_gfxwj",
        "name": "秦皇岛市规范性文件",
        "category": "市级",
        "region": "秦皇岛",
        "department": "市政府",
        "list_url": "http://www.qhd.gov.cn:81/info/list.jsp?deptid=58&code=293",
        "list_selectors": {
            "item": "a[href*='info/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "td::text"
        },
        "detail_selectors": {
            "title": "h1, .title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .content, .article-content",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    # 市财政局(信息公开平台)
    {
        "source_id": "city_qhd_czj_gk",
        "name": "秦皇岛市财政局(信息公开)",
        "category": "市级",
        "region": "秦皇岛",
        "department": "财政局",
        "list_url": "http://www.qhd.gov.cn:81/list.jsp?deptid=132&code=340",
        "list_selectors": {
            "item": "a[href*='info/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "td::text"
        },
        "detail_selectors": {
            "title": "h1, .title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .content, .article-content",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": False,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    # 市教育局
    qhd_config("city_qhd_jyj", "秦皇岛市教育局", "教育局",
               "http://jyj.qhd.gov.cn/home/list/?code=NjA0&pcode=MDE3NjMxOTgyNTE2"),
    # 市数据和政务服务局
    qhd_config("city_qhd_xzspj", "秦皇岛市数据和政务服务局", "数据和政务服务局",
               "http://xzspj.qhd.gov.cn/home/list/?code=NjI5&pcode=MDE3NjMxOTgyNTE2"),
    # 开发区
    {
        "source_id": "city_qhd_kfq",
        "name": "秦皇岛经济技术开发区",
        "category": "市级",
        "region": "秦皇岛",
        "department": "开发区",
        "list_url": "https://qetdz.gov.cn/Content/browse/cid/303",
        "list_selectors": {
            "item": "a[href*='/content/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    # 北戴河新区
    {
        "source_id": "city_qhd_bdhxq",
        "name": "北戴河新区",
        "category": "市级",
        "region": "秦皇岛",
        "department": "北戴河新区",
        "list_url": "http://www.bdhxq.gov.cn/",
        "list_selectors": {
            "item": "a[href*='/content/'], a[href*='/info/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    # 海港区
    {
        "source_id": "city_qhd_hgq",
        "name": "秦皇岛市海港区",
        "category": "区级",
        "region": "秦皇岛",
        "department": "海港区",
        "list_url": "https://www.qhdhgq.gov.cn/",
        "list_selectors": {
            "item": "a[href*='/content/'], a[href*='/info/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, .article-content, .content, .nr",
            "date": "meta[name=\"PubDate\"], .date"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 4,
        "request_interval_max": 6,
        "max_pages": 1,
    },
    # 待验证的 QHD 部门
    qhd_config("city_qhd_yjglj", "秦皇岛市应急管理局", "应急管理局",
               "http://yjglj.qhd.gov.cn/home/list/?code=NjEy&pcode=MDE3NjMxOTgyNTE2"),
    qhd_config("city_qhd_scjgj", "秦皇岛市市场监管局", "市场监管局",
               "http://scjgj.qhd.gov.cn/home/list/?code=NjE1&pcode=MDE3NjMxOTgyNTE2"),
    qhd_config("city_qhd_sfj", "秦皇岛市司法局", "司法局",
               "http://sfj.qhd.gov.cn/home/list/?code=NjEx&pcode=MDE3NjMxOTgyNTE2"),
    qhd_config("city_qhd_mzj", "秦皇岛市民政局", "民政局",
               "http://mzj.qhd.gov.cn/home/list/?code=NjAz&pcode=MDE3NjMxOTgyNTE2"),

    # ============ 河北省政府核心入口 ============
    # 政策文件总库（1689+条！）
    {
        "source_id": "prov_hebei_gov_zk",
        "name": "河北省政策文件总库",
        "category": "省级",
        "region": "河北",
        "department": "省政府",
        "list_url": "https://www.hebei.gov.cn/columns/49f13cc2-db03-4d0c-b4fe-2f3f659d3b6e/index.html",
        "list_selectors": {
            "item": "li a[href*='/columns/'], a[href*='/content/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span.date::text, .time::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 5,
        "request_interval_max": 8,
        "max_pages": 1,
    },
    # 政策解读
    {
        "source_id": "prov_hebei_gov_jd",
        "name": "河北省政策解读",
        "category": "省级",
        "region": "河北",
        "department": "省政府",
        "list_url": "https://www.hebei.gov.cn/columns/b4515201-74c2-4866-ba74-70199fee1a67/index.html",
        "list_selectors": {
            "item": "li a[href*='/columns/'], a[href*='/content/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span.date::text, .time::text"
        },
        "detail_selectors": {
            "title": "h1, .article-title",
            "content": ".TRS_Editor, #UCAP-CONTENT, .article-content, .content",
            "date": "meta[name=\"PubDate\"], .date, .time"
        },
        "render_js": True,
        "frequency": "daily",
        "request_interval_min": 5,
        "request_interval_max": 8,
        "max_pages": 1,
    },
    # 秦皇岛市信息公开政策专栏
    {
        "source_id": "city_qhd_gov_zc",
        "name": "秦皇岛市政策文件专栏",
        "category": "市级",
        "region": "秦皇岛",
        "department": "市政府",
        "list_url": "http://www.qhd.gov.cn/list_gz.jsp?code=342&type=zc",
        "list_selectors": {
            "item": "a[href*='info/']",
            "title": "a::text",
            "href": "a::attr(href)",
            "date": "span::text, td::text"
        },
        "detail_selectors": {
            "title": "h1, .title, .bt",
            "content": ".TRS_Editor, #UCAP-CONTENT, .content, .article-content",
            "date": "meta[name=\"PubDate\"], .date, .time"
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
    skipped = 0
    for src in SOURCES:
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

    print(f"\n创建 {created}，跳过 {skipped}")


if __name__ == "__main__":
    main()
