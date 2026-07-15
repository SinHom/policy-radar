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


# ---- 内容质量过滤 ----
# 垃圾正文特征（WAF 拦截、导航页、空壳页面等）
_GARBAGE_PATTERNS = [
    "403 Forbidden", "404 Not Found", "502 Bad Gateway",
    "云防护", "拒绝执行", "服务器拒绝执行该请求",
    "您访问的链接即将离开",
    # 2026-07-09 优化: 移除以下过严规则,避免 nav 误判
    # "网站地图", "站点地图", "sitemap",
    # "我要留言", "留言须知",
]
# 2026-07-09 优化: 放宽至 50 字符 (原 100)
_MIN_CONTENT_LENGTH = 50
_MIN_CHINESE_RATIO = 0.10  # 10% 中文

# 第 9 轮: 政策标题白名单, 命中可进一步降低阈值
_POLICY_TITLE_KEYWORDS = [
    "通知", "办法", "意见", "条例", "规定", "细则", "方案", "决定",
    "命令", "公告", "标准", "规范", "指南", "规则", "准则", "规程",
    "制度", "条文", "复函", "批复", "通报", "请示", "公告", "公示",
]

# 2026-07-09: 无价值标题黑名单（命中直接跳过）
_TITLE_JUNK_PATTERNS = [
    "邮箱", "通讯录", "联系", "联系方式",
    "询价函", "询价公告", "询价通知", "比选公告", "竞争性磋商", "磋商公告",
    "备案", "统计表", "汇总表", "情况统计",
    "目录", "索引", "列表", "清单", "总目录",
    "网页", "首页", "无标题", "入口", "导航",
    "检索", "搜索",
    "测试", "demo", "DEMO",
    "空标题",
    "无内容", "空白", "占位",
    "违规举报", "我要举报",
    "行政许可", "办事指南", "办事流程", "服务指南", "服务事项",
    "信用", "红黑名单",
    "年报", "年报数据", "统计公报", "统计报告",
]

# 2026-07-09: 无价值内容模式
_CONTENT_JUNK_PATTERNS = [
    "请输入关键字", "请输入关键词", "请输入搜索词", "请输入您要搜索",
    "请选择", "请选择地区", "请选择分类",
    "没有找到", "未找到相关", "无相关内容", "没有匹配",
    "登录后才能", "请先登录", "请登录后",
    "政务服务投诉", "国务院客户端", "扫码下载", "微信公众号",
    "手机版", "电脑版", "English",
]


def _is_garbage_content(text: str) -> bool:
    """检测正文是否是垃圾内容（WAF/导航/留言等）。"""
    text_lower = text.lower()
    for pat in _GARBAGE_PATTERNS:
        if pat.lower() in text_lower:
            return True
    return False


def _is_quality_content(text: str, title: str = "") -> bool:
    """正文是否达到质量标准：够长、中文占比够高、无垃圾特征。"""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped) < _MIN_CONTENT_LENGTH:
        return False
    if _is_garbage_content(stripped):
        return False
    # 中文字符占比
    chinese_chars = sum(1 for c in stripped if '一' <= c <= '鿿')
    ratio = chinese_chars / len(stripped) if stripped else 0
    if ratio < _MIN_CHINESE_RATIO:
        return False
    return True


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


# ---- 图片提取 ----
def extract_images(html: str, out_dir: Path, policy_id: int) -> list[tuple[str, str]]:
    """从 HTML 提取 base64/data URI 图片，保存到 out_dir，返回 [(md_image_text, abs_path), ...]。

    返回的 md_image_text 形如 ![alt](images/xxx.png)
    abs_path 是本地绝对路径（用于 markdown 引用）
    """
    if not html:
        return []
    import base64
    import re
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    imgs = soup.find_all("img")
    if not imgs:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    seen_data = set()  # 防重复

    for idx, img in enumerate(imgs):
        src = img.get("src", "")
        alt = img.get("alt", "") or f"image_{idx}"
        if not src:
            continue

        # 跳过外链（http/https）
        if src.startswith("http://") or src.startswith("https://"):
            # 不下载外部图片，只在 md 里加链接
            results.append((f"![{alt}]({src})\n", ""))
            continue

        # 处理 data: URI
        if src.startswith("data:"):
            m = re.match(r"data:image/(\w+);base64,(.+)", src)
            if not m:
                continue
            ext = m.group(1)
            if ext not in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
                ext = "png"
            b64 = m.group(2)

            # 去重: 同样的 base64 不重复保存
            h = hash(b64[:200])
            if h in seen_data:
                continue
            seen_data.add(h)

            try:
                img_bytes = base64.b64decode(b64)
            except Exception:
                continue

            # 文件名
            safe_alt = re.sub(r'[\\/:*?"<>|]', '_', alt)[:30].strip() or f"img_{idx}"
            filename = f"p{policy_id}_{idx:03d}_{safe_alt}.{ext}"
            img_path = out_dir / filename
            try:
                img_path.write_bytes(img_bytes)
                # md 引用相对路径 (相对 .md 所在目录)
                md_ref = f"images/{filename}"
                results.append((f"![{alt}]({md_ref})\n", str(img_path)))
            except Exception as e:
                logger.debug("保存图片失败: %s", e)
                continue

    return results


def is_image_heavy(html: str, text_threshold: int = 100) -> bool:
    """判断内容是否主要是图片（文字极少 + 多个 img）。"""
    if not html:
        return False
    import re
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(strip=True)
    n_imgs = len(soup.find_all("img"))
    # 文字 < 阈值 + 有图片 = 图片类
    # 一图读懂类的"一图+长标题"也算
    return n_imgs >= 1 and len(text) < text_threshold


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
    skipped_garbage = 0
    skipped_thin = 0
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

            # 2026-07-09 优化: 跳过明显是"首页/无标题/栏目页"等非具体政策文
            title_norm = (pol.title or "").strip()
            if title_norm in ('首页', '无标题', '主页', 'index', 'Index', '', '无', '首页/Index', '邮箱'):
                skipped_garbage += 1
                logger.debug("[SKIP] 首页/无标题/邮箱: %s | %s", src.source_id, pol.url)
                continue
            # URL 是 list/index 类的也跳过
            if pol.url and re.search(r'/(index|list|main|home|portal)[._/]?(\d*\.html?)?$', pol.url, re.I):
                skipped_garbage += 1
                logger.debug("[SKIP] 列表页 URL: %s | %s", src.source_id, pol.url)
                continue
            # 2026-07-09: 标题黑名单 (邮箱/询价函/统计表/通讯录/索引/目录 等)
            # 优化: 不限长度,只要标题含这些关键字就跳过
            is_junk_title = False
            for pat in _TITLE_JUNK_PATTERNS:
                if pat in title_norm:
                    is_junk_title = True
                    logger.debug("[SKIP] 垃圾标题 %s: %s", pat, title_norm[:50])
                    break
            if is_junk_title:
                skipped_garbage += 1
                continue

            # 转换内容
            md_content = html_to_md(pol.raw_content)
            if not md_content.strip():
                skipped_empty += 1
                continue

            # 质量过滤
            if not _is_quality_content(md_content):
                if len(md_content.strip()) < _MIN_CONTENT_LENGTH:
                    skipped_thin += 1
                else:
                    skipped_garbage += 1
                continue

            # 2026-07-09: 内容垃圾模式过滤
            is_content_junk = False
            for pat in _CONTENT_JUNK_PATTERNS:
                if pat in md_content and len(md_content) < 500:
                    is_content_junk = True
                    logger.debug("[SKIP] 内容垃圾 %s: %s", pat, title_norm)
                    break
            if is_content_junk:
                skipped_garbage += 1
                continue

            # 2026-07-09: 图片类文档处理 - 提取图片到子目录
            image_md_addition = ""
            if is_image_heavy(pol.raw_content, text_threshold=500):
                # 图片多 + 文字少 → 提取图片到 images/ 子目录
                img_dir = (out_path / reg / dep / str(year) / "images")
                extracted = extract_images(pol.raw_content, img_dir, pol.id)
                if extracted:
                    img_texts = [t[0] for t in extracted]
                    image_md_addition = "\n\n## 配图\n\n" + "".join(img_texts)
                    logger.info("提取 %d 张图片: %s", len(extracted), title_norm[:30])
                else:
                    # raw_content 中没有 <img> 标签 (spider 抓的是外部图片 URL)
                    # 添加 "需访问原文" 提示
                    image_md_addition = '\n\n> ⚠ **本文为图片解读类文档**（如 一图读懂 / 图解 等）\n> 原始 raw_content 中未含图片数据（spider 仅抓到文字 + nav）\n> 实际图表/配图需访问原文链接查看。\n> 后续可考虑用 Playwright 重抓 + 截图 + tesseract OCR 提取文字。\n'
                    logger.info("图片类文档无内嵌图片: %s", title_norm[:30])

            # 构建 MD 全文
            url_line = f"- 原文链接：{pol.url}" if pol.url else ""
            full_md = f"""# {pol.title}

- 来源：{src.name or src.source_id}
- 部门：{src.department or '-'}
- 地区：{src.region or '-'}
- 发布日期：{pub_date}
{url_line}

---

{md_content}{image_md_addition}
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

    stats = {
        "total": total, "exported": exported,
        "skipped_empty": skipped_empty, "skipped_thin": skipped_thin,
        "skipped_garbage": skipped_garbage, "errors": errors,
    }
    logger.info(
        "导出完成: total=%d exported=%d skipped_empty=%d skipped_thin=%d skipped_garbage=%d errors=%d",
        total, exported, skipped_empty, skipped_thin, skipped_garbage, errors,
    )
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
