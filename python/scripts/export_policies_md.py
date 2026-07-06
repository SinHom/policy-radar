"""政策原文导出为 Markdown 文件。

从 policies 表读取指定范围的政策，将 raw_content（HTML）转为 Markdown，
按 {region}/{department}/{year}/ 目录结构保存。

用法：
    python -m scripts.export_policies_md                          # 导出全部
    python -m scripts.export_policies_md --region hebei           # 仅河北
    python -m scripts.export_policies_md --region hebei,qhd       # 河北+秦皇岛
    python -m scripts.export_policies_md --days 730 --output ./out # 近2年
    python -m scripts.export_policies_md --limit 10 --dry-run     # 预览不写文件
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from python.models import Policy, PolicySource
from python.models.base import get_session, init_session_factory, make_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_md")

# 尝试加载 markdownify
try:
    from markdownify import markdownify as md_convert
except ImportError:
    md_convert = None
    logger.warning("markdownify 未安装，将保存原始 HTML。pip install markdownify")


# ---- 文件名字符清理 ----
_FILENAME_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def safe_filename(s: str, max_len: int = 50) -> str:
    """去掉不安全字符，截断。"""
    s = _FILENAME_SAFE_RE.sub("_", s)
    s = re.sub(r"\s+", "", s)
    return s[:max_len]


# ---- HTML → MD ----
def html_to_md(html: Optional[str]) -> str:
    """将 HTML 原文转为 Markdown，失败则返回纯文本。"""
    if not html:
        return ""
    if md_convert:
        try:
            return md_convert(html, heading_style="ATX", strip=["script", "style", "img"])
        except Exception:
            pass
    # fallback: 去掉 HTML 标签，保留文本
    from bs4 import BeautifulSoup
    try:
        return BeautifulSoup(html, "lxml").get_text("\n\n", strip=True)
    except Exception:
        return html


# ---- 核心导出逻辑 ----
async def export(
    *,
    region: Optional[list[str]] = None,
    source_ids: Optional[list[str]] = None,
    days: int = 730,
    output_dir: str = "data/exports/policies",
    dry_run: bool = False,
    limit: int = 0,
) -> dict:
    """导出政策为 MD 文件。

    返回 dict: {total, exported, skipped_empty, errors}
    """
    engine = make_engine()
    init_session_factory(engine)

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # 构建查询
    base_query = (
        select(Policy, PolicySource)
        .join(PolicySource, Policy.source_id == PolicySource.id)
        .where(Policy.crawled_at >= since)
    )

    # 按 source_id 过滤
    if source_ids:
        base_query = base_query.where(PolicySource.source_id.in_(source_ids))

    # 按 region 过滤（region 字段在 spider_config 或单独列中）
    # PolicySource.region 可能为 None，这里做模糊匹配
    if region:
        from sqlalchemy import or_
        conditions = []
        for r in region:
            r_lower = r.lower()
            conditions.append(PolicySource.region.ilike(f"%{r_lower}%"))
            conditions.append(PolicySource.source_id.ilike(f"%{r_lower}%"))
            conditions.append(PolicySource.name.ilike(f"%{r_lower}%"))
        base_query = base_query.where(or_(*conditions))

    base_query = base_query.order_by(Policy.published_at.desc())

    async with get_session() as session:
        result = await session.execute(base_query)
        rows = result.all()

    total = len(rows)
    logger.info("匹配 %d 条政策（since=%s, region=%s）", total, since.strftime("%Y-%m-%d"), region)

    if limit > 0:
        rows = rows[:limit]
        logger.info("限制导出 %d 条", limit)

    exported = 0
    skipped_empty = 0
    errors = 0
    out_path = Path(output_dir)

    for i, (pol, src) in enumerate(rows):
        try:
            # 确定目录：region/department/year/
            dep = (src.department or src.name or "other").strip()
            reg = (src.region or "other").strip()
            year = pol.published_at.year if pol.published_at else "unknown"
            dir_path = out_path / reg / dep / str(year)

            # 文件名：日期_source_id_标题
            pub_date = pol.published_at.isoformat() if pol.published_at else "nodate"
            title_short = safe_filename(pol.title or "untitled")
            filename = f"{pub_date}_{src.source_id}_{title_short}.md"

            # 转换内容
            md_content = html_to_md(pol.raw_content)
            if not md_content.strip():
                skipped_empty += 1
                logger.debug("跳过空内容: %s", pol.title)
                continue

            # 构建 MD 全文
            url_line = f"- 原文链接：{pol.url}" if pol.url else ""
            full_md = f"""# {pol.title}

- 来源：{src.name or src.source_id}
- 部门：{src.department or '-'}
- 地区：{src.region or '-'}
- 发布日期：{pub_date}
{url_line}

---

{md_content}
"""

            if dry_run:
                logger.info("[DRY RUN] %s/%s/%s", reg, dep, filename)
                exported += 1
            else:
                dir_path.mkdir(parents=True, exist_ok=True)
                file_path = dir_path / filename
                file_path.write_text(full_md, encoding="utf-8")
                exported += 1

            if (i + 1) % 100 == 0:
                logger.info("进度: %d/%d", exported, len(rows))

        except Exception as e:
            errors += 1
            logger.error("导出失败 [%s]: %s", getattr(pol, 'title', '?')[:50], e)

    stats = {"total": total, "exported": exported, "skipped_empty": skipped_empty, "errors": errors}
    logger.info("导出完成: total=%d exported=%d skipped=%d errors=%d", total, exported, skipped_empty, errors)
    return stats


# ---- CLI ----
def main() -> int:
    parser = argparse.ArgumentParser(description="政策原文导出为 Markdown")
    parser.add_argument("--region", type=str, default=None,
                        help="地区过滤，逗号分隔（如 'hebei,qhd'）")
    parser.add_argument("--source-ids", type=str, default=None,
                        help="source_id 过滤，逗号分隔")
    parser.add_argument("--days", type=int, default=730,
                        help="最近多少天（默认 730 = 2年）")
    parser.add_argument("--output", type=str, default="data/exports/policies",
                        help="输出目录（默认 data/exports/policies）")
    parser.add_argument("--limit", type=int, default=0,
                        help="限制导出条数（0=不限制）")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式，不写文件")
    args = parser.parse_args()

    region_list = [r.strip() for r in args.region.split(",") if r.strip()] if args.region else None
    source_id_list = [s.strip() for s in args.source_ids.split(",") if s.strip()] if args.source_ids else None

    stats = asyncio.run(export(
        region=region_list,
        source_ids=source_id_list,
        days=args.days,
        output_dir=args.output,
        dry_run=args.dry_run,
        limit=args.limit,
    ))

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}导出统计: {stats}")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
