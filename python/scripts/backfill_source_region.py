"""回填老 source 的 region/department/tags(原 migration 只加列、不回填)。

从 name 字段推断(例 "河北省发改委" → region=河北, department=发改委)。

跑法(容器内):
    docker exec policy-radar-app python /app/python/scripts/backfill_source_region.py
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

# ============== 省级名映射 ==============
PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
    "台湾", "香港", "澳门",
]

# ============== 部门后缀解析(委办) ==============
DEPT_PATTERNS = [
    # 委办(国家/省级)
    ("国家发展改革委", "发改委"), ("省发展改革委", "发改委"), ("省发改委", "发改委"),
    ("市发展改革委", "发改委"), ("市发改委", "发改委"),
    ("省工信厅", "工信厅"), ("市工信局", "工信局"), ("省经信厅", "经信厅"),
    ("市经信委", "经信委"), ("省工业和信息化厅", "工信厅"),
    ("省科技厅", "科技厅"), ("市科技局", "科技局"), ("市科创委", "科创委"),
    ("省教育厅", "教育厅"), ("市教育局", "教育局"),
    ("省人社厅", "人社厅"), ("市人社局", "人社局"),
    ("省财政厅", "财政厅"), ("市财政局", "财政局"),
    ("省自然资源厅", "自然资源厅"), ("省生态环境厅", "生态环境厅"),
    ("省住建厅", "住建厅"), ("省交通厅", "交通厅"), ("省水利厅", "水利厅"),
    ("省农业农村厅", "农业农村厅"), ("省商务厅", "商务厅"),
    ("省文旅厅", "文旅厅"), ("省卫健委", "卫健委"),
    ("省应急厅", "应急厅"), ("省审计厅", "审计厅"),
    ("省国资委", "国资委"), ("省市场监管局", "市场监管局"),
    ("省统计局", "统计局"), ("省金融监管局", "金融监管局"),
    ("省林草局", "林草局"), ("省药监局", "药监局"),
    ("省粮食局", "粮食局"), ("省民委", "民委"),
    ("省公安厅", "公安厅"), ("省民政厅", "民政厅"),
    ("省司法厅", "司法厅"),
    # 中央部委
    ("国务院", "国务院"), ("工信部", "工信部"), ("发改委", "发改委"),
    ("财政部", "财政部"), ("科技部", "科技部"), ("教育部", "教育部"),
    ("人社部", "人社部"), ("商务部", "商务部"), ("央行", "央行"),
    ("国家发改委", "发改委"), ("中国人民银行", "央行"),
]

# ============== 主推断函数 ==============
def infer_from_name(name: str) -> tuple[str | None, str | None]:
    """从 name="XXX" 推断 (region, department)。

    例: "河北省发改委" → ("河北", "发改委")
        "北京市经信局" → ("北京", "经信局")
        "深圳市发改委" → ("深圳", "发改委")
        "科技部" → (None, "科技部")
        "国家发改委" → ("全国", "发改委")
    """
    if not name:
        return None, None

    # 1) 国家级:以"国家"/"中国"/"国务院"开头
    if name.startswith(("国家", "中国", "国务院")) or name in ("央行", "财政部", "工信部", "科技部", "教育部", "人社部", "商务部"):
        return "全国", name

    # 2) 省级:看是否以"XX省"开头
    for prov in PROVINCES:
        if name.startswith(prov + "省"):
            rest = name[len(prov) + 1:]  # 去掉"河北省"
            # 进一步推断部门
            for pat, dept in DEPT_PATTERNS:
                if pat in rest or rest.startswith(pat):
                    return prov, dept
            return prov, rest

    # 3) 市级:看是否以"XX市"开头
    for prov in PROVINCES:
        if name.startswith(prov + "市"):
            rest = name[len(prov) + 1:]
            for pat, dept in DEPT_PATTERNS:
                if pat in rest or rest.startswith(pat):
                    return prov, dept
            return prov, rest

    # 4) 直接以部门名(无地域前缀)
    for pat, dept in DEPT_PATTERNS:
        if name == pat or name.startswith(pat):
            return None, dept

    return None, None


def main() -> None:
    _is_container = Path("/app/data").exists() and Path("/app/python").exists()
    db_path = "/app/data/policy_radar.db" if _is_container else "data/policy_radar.db"
    c = sqlite3.connect(db_path)
    rows = c.execute(
        "SELECT id, source_id, name, region, department, category FROM policy_sources "
        "WHERE (region IS NULL OR region = '' OR department IS NULL OR department = '')"
        "AND source_id NOT LIKE 'rss_%'"
    ).fetchall()
    print(f"待回填: {len(rows)}")

    updated = 0
    for sid_int, sid, name, old_region, old_dept, cat in rows:
        new_region, new_dept = infer_from_name(name)
        if new_region is None and new_dept is None:
            print(f"  ?  {sid:30s} {name:30s} → 推断失败,跳过")
            continue
        # 仅在原值缺失时更新
        if (old_region == new_region) and (old_dept == new_dept):
            continue
        c.execute(
            "UPDATE policy_sources SET region = ?, department = ? WHERE id = ?",
            (new_region, new_dept, sid_int),
        )
        updated += 1
        print(f"  ✓  {sid:30s} {name:30s} → region={new_region}, dept={new_dept}")
    c.commit()
    c.close()
    print(f"\n回填完成: {updated} 个源已更新")


if __name__ == "__main__":
    main()
