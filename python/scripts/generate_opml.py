"""生成信源的 OPML 订阅文件 + JSON 索引，方便导入 RSS 阅读器持续跟踪。

用法：
    python -m scripts.generate_opml                    # 生成 OPML + JSON
    python -m scripts.generate_opml --output ./feeds   # 指定输出目录
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import xml.dom.minidom as md
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gen_opml")

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # policy-radar/
RSSHUB_BASE = "https://rsshub.app"  # 公共 RSSHub 实例


def build_opml(sources: list[dict], title: str = "政策雷达·信源订阅") -> str:
    """生成 OPML 2.0 XML。"""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        '  <head>',
        f'    <title>{title}</title>',
        f'    <dateCreated>{now}</dateCreated>',
        f'    <description>政策雷达采集的政府信源列表 ({len(sources)} 个)</description>',
        '  </head>',
        '  <body>',
    ]

    # 按分类分组
    cats: dict[str, list[dict]] = {}
    for s in sources:
        cat = s.get("category", "其他") or "其他"
        cats.setdefault(cat, []).append(s)

    for cat_name, items in sorted(cats.items()):
        lines.append(f'    <outline text="{cat_name}" title="{cat_name}">')
        # 按部门再分组
        depts: dict[str, list[dict]] = {}
        for s in items:
            dept = s.get("department") or "其他"
            depts.setdefault(dept, []).append(s)

        for dept_name, dept_items in sorted(depts.items()):
            if dept_name and len(depts) > 1:
                lines.append(f'      <outline text="{dept_name}" title="{dept_name}">')
                prefix = "        "
            else:
                prefix = "      "

            for s in dept_items:
                name = s["name"]
                url = s.get("rss_url") or s.get("web_url", "")
                web_url = s.get("web_url", "")
                cnt = s.get("policy_count", 0)
                desc = f'{name} | 已采集{cnt}条 | Web: {web_url}'
                lines.append(
                    f'{prefix}<outline text="{name}" title="{name}" '
                    f'type="rss" xmlUrl="{url}" htmlUrl="{web_url}" '
                    f'description="{desc}"/>'
                )

            if dept_name and len(depts) > 1:
                lines.append(f'      </outline>')

        lines.append(f'    </outline>')

    lines.append('  </body>')
    lines.append('</opml>')

    xml_str = "\n".join(lines)
    # pretty print
    try:
        dom = md.parseString(xml_str)
        return dom.toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
    except Exception:
        return xml_str


async def generate(output_dir: str = "data/feeds") -> dict:
    """生成 OPML 和 JSON 索引文件。"""
    import sqlite3
    from python.models.base import make_engine

    engine = make_engine()
    db_path = engine.url.database
    conn = sqlite3.connect(db_path)

    rows = conn.execute('''
        SELECT s.source_id, s.name, s.category, s.department, s.region,
               json_extract(s.spider_config, "$.list_url") as web_url,
               COUNT(p.id) as policy_count
        FROM policy_sources s
        LEFT JOIN policies p ON s.id = p.source_id
        WHERE s.enabled = 1
        GROUP BY s.id
        ORDER BY s.category, s.department, s.name
    ''').fetchall()
    conn.close()

    # 加载 RSSHub 路由映射
    rsshub_map: dict[str, str] = {}
    rsshub_path = BASE_DIR / "rsshub_gov_paths.json"
    if rsshub_path.exists():
        try:
            with open(rsshub_path, encoding="utf-8") as f:
                rsshub_routes = json.load(f)
            for r in rsshub_routes:
                if r.get("path"):
                    # 提取文件名中的部门标识
                    file_key = r["file"].replace(".ts", "").replace("/", "_")
                    rsshub_map[file_key] = f"{RSSHUB_BASE}/gov{r['path']}"
        except Exception:
            pass

    sources = []
    for sid, name, cat, dept, region, web_url, cnt in rows:
        # 尝试匹配 RSSHub 路由
        rss_url = None
        for key, url in rsshub_map.items():
            # 模糊匹配：source_id 或 name 的部分在 RSSHub file key 中
            sid_parts = sid.replace("prov_hebei_", "").replace("city_qhd_", "").replace("city_sz_", "")
            if sid_parts in key or (dept and dept in key):
                rss_url = url
                break

        sources.append({
            "source_id": sid,
            "name": name,
            "category": cat or "其他",
            "department": dept or "",
            "region": region or "",
            "web_url": web_url or "",
            "rss_url": rss_url,
            "policy_count": cnt,
        })

    # 统计
    with_rss = sum(1 for s in sources if s["rss_url"])
    with_data = sum(1 for s in sources if s["policy_count"] > 0)
    logger.info("信源总数: %d | 有RSSHub路由: %d | 有数据: %d", len(sources), with_rss, with_data)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 生成 OPML（全部信源）
    opml = build_opml(sources)
    opml_path = out_dir / "policy_sources.opml"
    opml_path.write_text(opml, encoding="utf-8")
    logger.info("OPML: %s", opml_path)

    # 生成 JSON 索引
    json_path = out_dir / "policy_sources.json"
    json_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("JSON: %s", json_path)

    # 仅导出有 RSSHub 路由的
    rss_sources = [s for s in sources if s["rss_url"]]
    if rss_sources:
        rss_opml = build_opml(rss_sources, title="政策雷达·RSSHub订阅")
        rss_opml_path = out_dir / "policy_sources_rsshub.opml"
        rss_opml_path.write_text(rss_opml, encoding="utf-8")
        logger.info("RSSHub OPML: %s (%d 源)", rss_opml_path, len(rss_sources))

    stats = {
        "total_sources": len(sources),
        "with_rsshub": with_rss,
        "with_data": with_data,
        "opml": str(opml_path),
        "json": str(json_path),
    }
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="生成信源 OPML 订阅文件")
    parser.add_argument("--output", type=str, default="data/feeds", help="输出目录")
    args = parser.parse_args()

    stats = asyncio.run(generate(output_dir=args.output))
    print(f"\n生成完成: {json.dumps(stats, ensure_ascii=False, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
