"""一次性补 河北 22 委办 + 11 地市源(placeholder,等用户填 URL)。

这些源是 placeholder:
- name/region/department/category 填好
- url 暂用 河北省政府门户 heb.gov.cn 的政策栏目(很多会 404,标 last_status='pending')
- enabled=0,用户可单独启用并编辑 URL

跑法(容器内):
    docker exec policy-radar-app python /app/python/scripts/add_hebei_sources.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# 河北 22 委办
HEBEI_DEPT_OFFICES = [
    ("fgw",  "河北省发改委",       "发改委"),
    ("gxj",  "河北省工信厅",       "工信厅"),
    ("jyt",  "河北省教育厅",       "教育厅"),
    ("kjt",  "河北省科技厅",       "科技厅"),
    ("mzw",  "河北省民委",         "民委"),
    ("gaj",  "河北省公安厅",       "公安厅"),
    ("mzj",  "河北省民政厅",       "民政厅"),
    ("sft",  "河北省司法厅",       "司法厅"),
    # ("czt",  "河北省财政厅",       "财政厅"),  # 已有 rss_hebei_czt_xwdt
    ("rst",  "河北省人社厅",       "人社厅"),
    ("zrzc", "河北省自然资源厅",   "自然资源厅"),
    ("sthj", "河北省生态环境厅",   "生态环境厅"),
    ("zfcx", "河北省住建厅",       "住建厅"),
    ("jtw",  "河北省交通厅",       "交通厅"),
    ("slt",  "河北省水利厅",       "水利厅"),
    ("nyj",  "河北省农业农村厅",   "农业农村厅"),
    ("swt",  "河北省商务厅",       "商务厅"),
    ("wlt",  "河北省文旅厅",       "文旅厅"),
    ("wjw",  "河北省卫健委",       "卫健委"),
    ("yjj",  "河北省应急厅",       "应急厅"),
    ("sjt",  "河北省审计厅",       "审计厅"),
    ("gzw",  "河北省国资委",       "国资委"),
]

# 河北 11 地级市
HEBEI_CITIES = [
    ("sjz",  "石家庄"),
    ("tang", "唐山"),
    ("qhd",  "秦皇岛"),
    ("hd",   "邯郸"),
    ("xt",   "邢台"),
    ("bd",   "保定"),
    ("zjk",  "张家口"),
    ("cd",   "承德"),
    ("cz",   "沧州"),
    ("lf",   "廊坊"),
    ("hs",   "衡水"),
]


def main() -> None:
    _is_container = Path("/app/data").exists() and Path("/app/python").exists()
    db_path = "/app/data/policy_radar.db" if _is_container else "data/policy_radar.db"
    spiders_dir = Path("/app/python/crawlers/spiders") if _is_container else Path("python/crawlers/spiders")
    spiders_dir.mkdir(parents=True, exist_ok=True)

    c = sqlite3.connect(db_path)
    now = __import__("datetime").datetime.utcnow().isoformat()
    inserted = updated = spider_new = 0

    # 委办
    for short_id, name, dept_short in HEBEI_DEPT_OFFICES:
        sid = f"hb_{short_id}"
        url = f"https://www.hebei.gov.cn/columns/{short_id}/zwgk"  # 占位 URL
        existing = c.execute("SELECT id FROM policy_sources WHERE source_id = ?", (sid,)).fetchone()
        if existing:
            updated += 1
            continue
        c.execute(
            """INSERT INTO policy_sources
               (source_id, name, url, category, region, department,
                spider_config, frequency, enabled, last_status, created_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'daily', 0, 'pending', ?, ?)""",
            (sid, name, url, "省级", "河北", name,
             json.dumps({"mode": "playwright", "list_url": url,
                         "notes": "河北省XX厅占位源,需要编辑 URL + CSS 选择器才能爬",
                         "placeholder": True}, ensure_ascii=False),
             now, json.dumps(["省级", "河北", name, "placeholder"], ensure_ascii=False)),
        )
        spider_path = spiders_dir / f"{sid}.json"
        if not spider_path.exists():
            spider_path.write_text(json.dumps({
                "source_id": sid, "name": name, "category": "省级",
                "region": "河北", "department": name, "list_url": url,
                "mode": "playwright", "render_js": True, "frequency": "daily",
                "request_interval_min": 5, "request_interval_max": 10, "max_pages": 1,
                "notes": "河北省XX厅占位源,需要编辑 URL + CSS 选择器",
                "placeholder": True,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            spider_new += 1
        inserted += 1
        print(f"  + {sid:20s} {name}")

    # 地市
    for short_id, name in HEBEI_CITIES:
        sid = f"hb_city_{short_id}"
        url = f"https://www.{short_id}.gov.cn/zwgk"  # 占位 URL
        existing = c.execute("SELECT id FROM policy_sources WHERE source_id = ?", (sid,)).fetchone()
        if existing:
            updated += 1
            continue
        full_dept = f"{name}市政府"
        c.execute(
            """INSERT INTO policy_sources
               (source_id, name, url, category, region, department,
                spider_config, frequency, enabled, last_status, created_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'daily', 0, 'pending', ?, ?)""",
            (sid, f"河北-{name}政府", url, "市级", "河北", full_dept,
             json.dumps({"mode": "playwright", "list_url": url,
                         "notes": "河北省地市政府占位源,需要编辑 URL + CSS 选择器",
                         "placeholder": True}, ensure_ascii=False),
             now, json.dumps(["市级", "河北", full_dept, "placeholder"], ensure_ascii=False)),
        )
        spider_path = spiders_dir / f"{sid}.json"
        if not spider_path.exists():
            spider_path.write_text(json.dumps({
                "source_id": sid, "name": f"河北-{name}政府", "category": "市级",
                "region": "河北", "department": full_dept, "list_url": url,
                "mode": "playwright", "render_js": True, "frequency": "daily",
                "request_interval_min": 5, "request_interval_max": 10, "max_pages": 1,
                "notes": "河北省地市政府占位源,需要编辑 URL + CSS 选择器",
                "placeholder": True,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            spider_new += 1
        inserted += 1
        print(f"  + {sid:20s} 河北-{name}政府")

    c.commit()
    c.close()
    print(f"\n河北源补完: DB 新增 {inserted} / 已存在 {updated} / spider 新建 {spider_new}")


if __name__ == "__main__":
    main()
