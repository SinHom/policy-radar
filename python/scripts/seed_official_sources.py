"""批量 seed 官方政策源：国家级 + 重点省级 + 重点城市。

使用：python -m scripts.seed_official_sources
- 会跳过已存在的 source_id
- 全部 enabled=True
- 全部带 region / department / tags 标签
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import select

from python.models.base import get_session, init_session_factory, make_engine
from python.models.policy_source import PolicySource

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# === 国家级 ===
NATIONAL = [
    {
        "source_id": "nat_gov_cn", "name": "中国政府网（国务院）",
        "category": "国家级", "region": "全国", "department": "国务院",
        "tags": ["国家级", "国务院", "政策"],
        "list_url": "https://www.gov.cn/zhengce/zhengceku/2024-04/29/content_6947000.htm",
        "frequency": "daily",
    },
    {
        "source_id": "nat_ndrc", "name": "国家发改委",
        "category": "国家级", "region": "全国", "department": "发改委",
        "tags": ["国家级", "发改", "产业政策"],
        "list_url": "https://www.ndrc.gov.cn/xxgk/zcfb/tz/index.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_miit", "name": "工信部",
        "category": "国家级", "region": "全国", "department": "工信",
        "tags": ["国家级", "工信", "制造业"],
        "list_url": "https://www.miit.gov.cn/jgsj/zbys/wjfb/art/2024/art_34e3a4f9d2e44f0c8a1f8a2b8d1e3f0c.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_most", "name": "科技部",
        "category": "国家级", "region": "全国", "department": "科技",
        "tags": ["国家级", "科技", "高新"],
        "list_url": "https://www.most.gov.cn/xxgk/xinxifenlei/fdzdgknr/zfwj/index.htm",
        "frequency": "daily",
    },
    {
        "source_id": "nat_mof", "name": "财政部",
        "category": "国家级", "region": "全国", "department": "财政",
        "tags": ["国家级", "财政", "税收"],
        "list_url": "http://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/index.htm",
        "frequency": "daily",
    },
    {
        "source_id": "nat_mohrss", "name": "人社部",
        "category": "国家级", "region": "全国", "department": "人社",
        "tags": ["国家级", "人社", "人才"],
        "list_url": "http://www.mohrss.gov.cn/SYrlzyhshbzb/zwgk/rdzc/index.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_mofcom", "name": "商务部",
        "category": "国家级", "region": "全国", "department": "商务",
        "tags": ["国家级", "商务", "外贸"],
        "list_url": "https://www.mofcom.gov.cn/article/zwgk/zcfb/index.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_tax", "name": "国家税务总局",
        "category": "国家级", "region": "全国", "department": "税务",
        "tags": ["国家级", "税务", "税收"],
        "list_url": "https://www.chinatax.gov.cn/chinatax/n810341/n810825/index.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_mee", "name": "生态环境部",
        "category": "国家级", "region": "全国", "department": "环保",
        "tags": ["国家级", "环保", "绿色"],
        "list_url": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/index.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_moa", "name": "农业农村部",
        "category": "国家级", "region": "全国", "department": "农业",
        "tags": ["国家级", "农业", "乡村振兴"],
        "list_url": "https://www.moa.gov.cn/nyb/policy/index.htm",
        "frequency": "daily",
    },
    {
        "source_id": "nat_sasac", "name": "国资委",
        "category": "国家级", "region": "全国", "department": "国资",
        "tags": ["国家级", "国资", "国企"],
        "list_url": "http://www.sasac.gov.cn/n2588035/n2641579/index.html",
        "frequency": "weekly",
    },
    {
        "source_id": "nat_stats", "name": "国家统计局",
        "category": "国家级", "region": "全国", "department": "统计",
        "tags": ["国家级", "统计", "数据"],
        "list_url": "https://www.stats.gov.cn/sj/zxfb/index.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_cbirc", "name": "国家金融监督管理总局",
        "category": "国家级", "region": "全国", "department": "金融",
        "tags": ["国家级", "金融", "监管"],
        "list_url": "https://www.nfra.gov.cn/cn/view/pages/ItemList.html?itemPId=1244&itemId=1244&itemUrl=ItemListRightList.html",
        "frequency": "daily",
    },
    {
        "source_id": "nat_csrc", "name": "证监会",
        "category": "国家级", "region": "全国", "department": "证券",
        "tags": ["国家级", "证券", "资本"],
        "list_url": "http://www.csrc.gov.cn/csrc/c100217/common_list.shtml",
        "frequency": "daily",
    },
    {
        "source_id": "nat_samr", "name": "国家市场监管总局",
        "category": "国家级", "region": "全国", "department": "市场监管",
        "tags": ["国家级", "市场监管", "标准"],
        "list_url": "https://www.samr.gov.cn/xw/zj/index.html",
        "frequency": "daily",
    },
]

# === 重点省级（北上广深 + 强省） ===
PROVINCIAL = [
    {"source_id": "prov_bj_fgw", "name": "北京市发改委", "category": "省级", "region": "北京", "department": "发改",
     "tags": ["省级", "北京", "发改"], "list_url": "https://fgw.beijing.gov.cn/zwxx/tzgg/index.html"},
    {"source_id": "prov_bj_gxj", "name": "北京市经信局", "category": "省级", "region": "北京", "department": "工信",
     "tags": ["省级", "北京", "工信"], "list_url": "https://jxj.beijing.gov.cn/zwxx/2024zcwj/index.html"},
    {"source_id": "prov_bj_kjj", "name": "北京市科委", "category": "省级", "region": "北京", "department": "科技",
     "tags": ["省级", "北京", "科技"], "list_url": "https://kw.beijing.gov.cn/col/col7357/index.html"},
    {"source_id": "prov_sh_fgw", "name": "上海市发改委", "category": "省级", "region": "上海", "department": "发改",
     "tags": ["省级", "上海", "发改"], "list_url": "https://fgw.sh.gov.cn/2024-zfwj/index.html"},
    {"source_id": "prov_sh_jxj", "name": "上海市经信委", "category": "省级", "region": "上海", "department": "工信",
     "tags": ["省级", "上海", "工信"], "list_url": "https://sheitc.sh.gov.cn/2024-zfwj/index.html"},
    {"source_id": "prov_sh_kjj", "name": "上海市科委", "category": "省级", "region": "上海", "department": "科技",
     "tags": ["省级", "上海", "科技"], "list_url": "https://stcsm.sh.gov.cn/2024-zfwj/index.html"},
    {"source_id": "prov_gd_fgw", "name": "广东省发改委", "category": "省级", "region": "广东", "department": "发改",
     "tags": ["省级", "广东", "发改"], "list_url": "http://drc.gd.gov.cn/ywtz/index.html"},
    {"source_id": "prov_gd_gxj", "name": "广东省工信厅", "category": "省级", "region": "广东", "department": "工信",
     "tags": ["省级", "广东", "工信"], "list_url": "http://gdii.gd.gov.cn/zwgk/zcwjk/index.html"},
    {"source_id": "prov_gd_kjj", "name": "广东省科技厅", "category": "省级", "region": "广东", "department": "科技",
     "tags": ["省级", "广东", "科技"], "list_url": "http://gdinfo.gd.gov.cn/zwgk/zcwjk/index.html"},
    {"source_id": "prov_gd_tax", "name": "广东省税务局", "category": "省级", "region": "广东", "department": "税务",
     "tags": ["省级", "广东", "税务"], "list_url": "https://guangdong.chinatax.gov.cn/siteapps/webpage/gd/index.html"},
    {"source_id": "prov_js_gxj", "name": "江苏省工信厅", "category": "省级", "region": "江苏", "department": "工信",
     "tags": ["省级", "江苏", "工信"], "list_url": "https://gxt.jiangsu.gov.cn/col/col9176/index.html"},
    {"source_id": "prov_zj_jxj", "name": "浙江省经信厅", "category": "省级", "region": "浙江", "department": "工信",
     "tags": ["省级", "浙江", "工信"], "list_url": "https://jxt.zj.gov.cn/col/col1229563842/index.html"},
    {"source_id": "prov_zj_kjt", "name": "浙江省科技厅", "category": "省级", "region": "浙江", "department": "科技",
     "tags": ["省级", "浙江", "科技"], "list_url": "https://kjt.zj.gov.cn/col/col1229707390/index.html"},
    {"source_id": "prov_sd_gxt", "name": "山东省工信厅", "category": "省级", "region": "山东", "department": "工信",
     "tags": ["省级", "山东", "工信"], "list_url": "http://gxt.shandong.gov.cn/col/col9149/index.html"},
    {"source_id": "prov_fj_gxt", "name": "福建省工信厅", "category": "省级", "region": "福建", "department": "工信",
     "tags": ["省级", "福建", "工信"], "list_url": "https://gxt.fujian.gov.cn/zwgk/2024zcwj/index.html"},
    {"source_id": "prov_sc_jxj", "name": "四川省经信厅", "category": "省级", "region": "四川", "department": "工信",
     "tags": ["省级", "四川", "工信"], "list_url": "https://jxt.sc.gov.cn/scjxj/zcwjk/2024/12/4/c0c8f7a3a8c0a4b7d8e6f/index.html"},
    {"source_id": "prov_hn_gxt", "name": "河南省工信厅", "category": "省级", "region": "河南", "department": "工信",
     "tags": ["省级", "河南", "工信"], "list_url": "https://gxt.henan.gov.cn/zwgk/zcwjk/index.html"},
    {"source_id": "prov_hb_gxt", "name": "湖北省经信厅", "category": "省级", "region": "湖北", "department": "工信",
     "tags": ["省级", "湖北", "工信"], "list_url": "https://jxt.hubei.gov.cn/fbjd/xxgkml/2024zcwj/index.html"},
]

# === 重点市级 ===
CITY = [
    {"source_id": "city_bj_gxj", "name": "北京市经信局", "category": "市级", "region": "北京", "department": "工信",
     "tags": ["市级", "北京", "工信"], "list_url": "https://jxj.beijing.gov.cn/zwxx/2024zcwj/index.html"},
    {"source_id": "city_sh_jxj", "name": "上海市经信委", "category": "市级", "region": "上海", "department": "工信",
     "tags": ["市级", "上海", "工信"], "list_url": "https://sheitc.sh.gov.cn/2024-zfwj/index.html"},
    {"source_id": "city_sz_gxj", "name": "深圳市工信局", "category": "市级", "region": "深圳", "department": "工信",
     "tags": ["市级", "深圳", "工信"], "list_url": "https://gxj.sz.gov.cn/zwgk/xxgkml/zfxxgkml/zfxxgkmlgkml/index.html"},
    {"source_id": "city_sz_fgw", "name": "深圳市发改委", "category": "市级", "region": "深圳", "department": "发改",
     "tags": ["市级", "深圳", "发改"], "list_url": "https://fgw.sz.gov.cn/zwgk/qtxxgkml/zfwj/index.html"},
    {"source_id": "city_sz_kjj", "name": "深圳市科创委", "category": "市级", "region": "深圳", "department": "科技",
     "tags": ["市级", "深圳", "科技"], "list_url": "https://stic.sz.gov.cn/zwgk/zfwj/index.html"},
    {"source_id": "city_sz_hrss", "name": "深圳市人社局", "category": "市级", "region": "深圳", "department": "人社",
     "tags": ["市级", "深圳", "人社"], "list_url": "https://hrss.sz.gov.cn/zwgk/zfwj/index.html"},
    {"source_id": "city_sz_tax", "name": "深圳市税务局", "category": "市级", "region": "深圳", "department": "税务",
     "tags": ["市级", "深圳", "税务"], "list_url": "https://shenzhen.chinatax.gov.cn/siteapps/webpage/sz/index.html"},
    {"source_id": "city_gz_gxj", "name": "广州市工信局", "category": "市级", "region": "广州", "department": "工信",
     "tags": ["市级", "广州", "工信"], "list_url": "https://gxj.gz.gov.cn/zwgk/2024zcwj/index.html"},
    {"source_id": "city_hz_jxj", "name": "杭州市经信局", "category": "市级", "region": "杭州", "department": "工信",
     "tags": ["市级", "杭州", "工信"], "list_url": "https://jxj.hangzhou.gov.cn/col/col1229416425/index.html"},
    {"source_id": "city_cd_jxj", "name": "成都市经信局", "category": "市级", "region": "成都", "department": "工信",
     "tags": ["市级", "成都", "工信"], "list_url": "https://cdjx.chengdu.gov.cn/cdjxj/zcwjk/2024/12/4/index.html"},
]

# === 重点区级 ===
DISTRICT = [
    {"source_id": "dist_bj_hd", "name": "北京海淀区", "category": "区级", "region": "北京", "department": "综合",
     "tags": ["区级", "海淀", "北京"], "list_url": "https://www.bjhd.gov.cn/xxgk/2024zcwj/index.html"},
    {"source_id": "dist_bj_cz", "name": "北京朝阳区", "category": "区级", "region": "北京", "department": "综合",
     "tags": ["区级", "朝阳", "北京"], "list_url": "https://www.bjchy.gov.cn/xxgk/2024zcwj/index.html"},
    {"source_id": "dist_sh_pd", "name": "上海浦东新区", "category": "区级", "region": "上海", "department": "综合",
     "tags": ["区级", "浦东", "上海"], "list_url": "https://www.pudong.gov.cn/zwgk/2024zcwj/index.html"},
    {"source_id": "dist_sz_ns", "name": "深圳南山区", "category": "区级", "region": "深圳", "department": "综合",
     "tags": ["区级", "南山", "深圳"], "list_url": "https://www.szns.gov.cn/xxgk/2024zcwj/index.html"},
    {"source_id": "dist_sz_ft", "name": "深圳福田区", "category": "区级", "region": "深圳", "department": "综合",
     "tags": ["区级", "福田", "深圳"], "list_url": "https://www.szft.gov.cn/xxgk/2024zcwj/index.html"},
    {"source_id": "dist_gz_th", "name": "广州天河区", "category": "区级", "region": "广州", "department": "综合",
     "tags": ["区级", "天河", "广州"], "list_url": "https://www.thnet.gov.cn/xxgk/2024zcwj/index.html"},
]

ALL_SOURCES = NATIONAL + PROVINCIAL + CITY + DISTRICT


# 标准 selectors（最常见政府网站）
DEFAULT_SELECTORS = {
    "list_selectors": {
        "item": "ul li a, .article-list a, .news-list a, .list-article a, li a",
        "title": "a::text",
        "href": "a::attr(href)",
        "date": "span.date, .date, em.date",
    },
    "detail_selectors": {
        "title": "h1, h1.article-title, .article-title",
        "content": "div.article-content, .content, article, .article-body",
        "date": ".pub-date, .date",
    },
}


async def seed():
    from python.app.config import get_settings
    settings = get_settings()
    engine = make_engine(settings.database_url or None)
    init_session_factory(engine)
    try:
        async with get_session() as session:
            added = 0
            skipped = 0
            for cfg in ALL_SOURCES:
                # 查重
                existing = (await session.execute(
                    select(PolicySource).where(PolicySource.source_id == cfg["source_id"])
                )).scalar_one_or_none()
                if existing:
                    skipped += 1
                    continue
                src = PolicySource(
                    source_id=cfg["source_id"],
                    name=cfg["name"],
                    url=cfg.get("list_url"),
                    category=cfg.get("category"),
                    region=cfg.get("region"),
                    department=cfg.get("department"),
                    tags=cfg.get("tags", []),
                    spider_config=DEFAULT_SELECTORS,
                    frequency=cfg.get("frequency", "daily"),
                    enabled=True,
                )
                session.add(src)
                added += 1
            await session.commit()
            logger.info("✅ seed done: added=%d, skipped=%d, total=%d",
                        added, skipped, len(ALL_SOURCES))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
