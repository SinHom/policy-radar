"""政策雷达 - RSS / Markdown 输出端点。

- GET /policy-radar/feed             → RSS 2.0 列表（按 query 筛选）
- GET /policy-radar/feed/{region}    → 按地区筛选
- GET /policy-radar/feed/{region}/{dept}  → 按地区+部门
- GET /policy-radar/article/{id}     → 单篇政策 (Markdown-in-RSS)
- GET /policy-radar/markdown/{id}    → 纯 Markdown 文本（带 YAML frontmatter, 适合知识库直接抓）
- GET /policy-radar/opml             → 所有源的 OPML 订阅列表

支持 query 参数:
  tag=惠企_政策,解读
  from=2026-01-01
  to=2026-07-09
  limit=50 (默认 30, 最大 200)
  full=1 (列表里也包含完整 markdown)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date
from typing import Any, Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, or_, func

from python.crawlers.tagger import classify_tags
from python.models import Policy, PolicySource
from python.models.base import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/policy-radar", tags=["policy-radar-rss"])

# markdownify 延迟导入（避免启动时强制依赖）
_md_convert = None


def get_md_convert():
    global _md_convert
    if _md_convert is None:
        try:
            from markdownify import markdownify
            _md_convert = markdownify
        except ImportError:
            logger.warning("markdownify 未安装,fallback 到简单 HTML→text")
            _md_convert = None
    return _md_convert


def html_to_clean_markdown(html: str) -> str:
    """HTML → 干净 Markdown（去除 nav/script/style，保留核心正文）。"""
    if not html:
        return ""
    text = html
    # 去除明显 nav/footer/script/style
    text = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", "", text, flags=re.I | re.S)
    text = re.sub(r"<nav\b[^<]*(?:(?!</nav>)<[^<]*)*</nav>", "", text, flags=re.I | re.S)
    text = re.sub(r"<footer\b[^<]*(?:(?!</footer>)<[^<]*)*</footer>", "", text, flags=re.I | re.S)
    text = re.sub(r"<header\b[^<]*(?:(?!</header>)<[^<]*)*</header>", "", text, flags=re.I | re.S)
    md = get_md_convert()
    if md:
        return md(text, heading_style="atx", bullet_list_marker="-").strip()
    # fallback
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def build_frontmatter(p: dict) -> str:
    lines = ["---"]
    lines.append(f"id: {p['id']}")
    lines.append(f"title: {json.dumps(p['title'], ensure_ascii=False)}")
    lines.append(f"url: {json.dumps(p['url'], ensure_ascii=False)}")
    lines.append(f"source: {json.dumps(p.get('source_name', ''), ensure_ascii=False)}")
    if p.get("department"):
        lines.append(f"department: {json.dumps(p['department'], ensure_ascii=False)}")
    if p.get("region"):
        lines.append(f"region: {json.dumps(p['region'], ensure_ascii=False)}")
    if p.get("published_at"):
        lines.append(f"published_at: {json.dumps(p['published_at'], ensure_ascii=False)}")
    if p.get("tags"):
        lines.append(f"tags: [{', '.join(json.dumps(t, ensure_ascii=False) for t in p['tags'])}]")
    if p.get("summary"):
        lines.append(f"summary: {json.dumps(p['summary'], ensure_ascii=False)}")
    if p.get("advisory"):
        lines.append(f"advisory: {json.dumps(p['advisory'], ensure_ascii=False)}")
    if p.get("crawled_at"):
        lines.append(f"crawled_at: {json.dumps(p['crawled_at'], ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def parse_tags(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


async def _query_policies(
    region: Optional[str],
    dept: Optional[str],
    tags: Optional[list[str]],
    date_from: Optional[date],
    date_to: Optional[date],
    limit: int,
) -> list[dict]:
    """查询政策构建 RSS item。tags 过滤在 item 构建后于 Python 层进行（AND
    语义），作用于 merge 后的标签（源级 + 标题级），故 ?tag= 可命中标题级
    标签；tags 非空时不施加 SQL limit，取回全量过滤后再截断到 limit。"""
    async with get_session() as session:
        stmt = (
            select(Policy, PolicySource)
            .join(PolicySource, Policy.source_id == PolicySource.id)
            .where(func.length(Policy.raw_content) > 50)
        )
        if region:
            stmt = stmt.where(PolicySource.region.ilike(f"%{region}%"))
        if dept:
            stmt = stmt.where(
                or_(
                    PolicySource.department.ilike(f"%{dept}%"),
                    PolicySource.name.ilike(f"%{dept}%"),
                )
            )
        if date_from:
            stmt = stmt.where(Policy.published_at >= date_from)
        if date_to:
            stmt = stmt.where(Policy.published_at <= date_to)
        # tags 过滤移至 item 构建后（按 merged tags 含标题级标签过滤），见函数末尾。
        # 排序：published_at 优先（NULL 排最后）
        stmt = stmt.order_by(Policy.published_at.desc().nulls_last(), Policy.crawled_at.desc())
        # tags 非空时不施加 SQL limit（需全量取回后按 merged tags 过滤再截断）
        if not tags:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        out = []
        for pol, src in result.all():
            out.append({
                "id": pol.id,
                "source_id": src.source_id,
                "url": pol.url,
                "title": pol.title,
                "raw_content": pol.raw_content or "",
                "published_at": pol.published_at.isoformat() if pol.published_at else None,
                "crawled_at": pol.crawled_at.isoformat() if pol.crawled_at else None,
                "summary": pol.summary_text or "",
                "advisory": pol.advisory or "",
                "source_name": src.name,
                "department": src.department or "",
                "region": src.region or "other",
                "tags": list(dict.fromkeys(
                    parse_tags(src.tags) + classify_tags(pol.title)
                )),
            })
        # tags 过滤：在 merged tags（含标题级标签）上 AND 匹配，再截断到 limit
        if tags:
            out = [p for p in out if all(t in p["tags"] for t in tags)][:limit]
        return out


def _build_rss_xml(title: str, link: str, description: str, items: list[dict], base_url: str) -> str:
    """构建 RSS 2.0 XML。"""
    now_str = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        f'<title>{escape(title)}</title>',
        f'<link>{escape(link)}</link>',
        f'<description>{escape(description)}</description>',
        f'<lastBuildDate>{now_str}</lastBuildDate>',
        '<generator>policy-radar v0.3</generator>',
    ]
    for it in items:
        pub_date = it["published_at"] or it["crawled_at"] or now_str
        if isinstance(pub_date, str) and len(pub_date) == 10:
            pub_date_str = f"{pub_date}T00:00:00 +0000"
        elif isinstance(pub_date, str):
            pub_date_str = pub_date
        else:
            pub_date_str = now_str
        # 简化成 RFC822
        try:
            dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00").replace("+0000", ""))
            pub_date_str = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            pub_date_str = now_str

        article_url = f"{base_url}/policy-radar/markdown/{it['id']}"
        cat_xml = "".join(f"<category>{escape(t)}</category>" for t in (it.get("tags") or []))
        xml_parts.append("<item>")
        xml_parts.append(f"<title>{escape(it['title'])}</title>")
        xml_parts.append(f"<link>{escape(it['url'])}</link>")
        xml_parts.append(f"<guid isPermaLink=\"false\">policy-radar-{it['id']}</guid>")
        xml_parts.append(f"<pubDate>{pub_date_str}</pubDate>")
        xml_parts.append(f"<author>{escape(it.get('department') or it.get('source_name') or '')}</author>")
        if cat_xml:
            xml_parts.append(cat_xml)
        # description
        desc_parts = []
        if it.get("summary"):
            desc_parts.append(f"<p><strong>摘要：</strong>{escape(it['summary'])}</p>")
        if it.get("tags"):
            tag_html = " ".join(f"<code>{escape(t)}</code>" for t in it['tags'])
            desc_parts.append(f"<p><strong>标签：</strong> {tag_html}</p>")
        desc_parts.append(
            f"<p><strong>地区：</strong>{escape(it.get('region') or '其他')} | "
            f"<strong>部门：</strong>{escape(it.get('department') or it.get('source_name') or '')} | "
            f"<strong>发布日期：</strong>{escape(it.get('published_at') or '未知')}</p>"
        )
        desc_parts.append(
            f'<p><a href="{escape(article_url)}">下载完整 Markdown →</a></p>'
        )
        xml_parts.append(f"<description><![CDATA[{''.join(desc_parts)}]]></description>")
        xml_parts.append("</item>")
    xml_parts.append("</channel></rss>")
    return "\n".join(xml_parts)


@router.get("/feed", response_class=Response)
@router.get("/feed/{region}", response_class=Response)
@router.get("/feed/{region}/{dept}", response_class=Response)
async def get_feed(
    region: Optional[str] = None,
    dept: Optional[str] = None,
    tag: Optional[str] = Query(default=None, description="逗号分隔多选"),
    from_: Optional[str] = Query(default=None, alias="from", description="起始日期 YYYY-MM-DD"),
    to: Optional[str] = Query(default=None, description="截止日期 YYYY-MM-DD"),
    limit: int = Query(default=30, ge=1, le=200),
    full: int = Query(default=0, description="1=列表内含完整 markdown"),
):
    """RSS 2.0 列表。可按 region/dept/tag/date 筛选。"""
    base = "http://localhost:8000"  # 由前置代理 / nginx 改写

    tags = [t.strip() for t in (tag or "").split(",") if t.strip()] if tag else None
    date_from = None
    date_to = None
    try:
        if from_:
            date_from = datetime.strptime(from_, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "from 必须是 YYYY-MM-DD")
    try:
        if to:
            date_to = datetime.strptime(to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "to 必须是 YYYY-MM-DD")

    policies = await _query_policies(region, dept, tags, date_from, date_to, limit)
    items = policies  # for build_rss
    title_parts = ["政策雷达"]
    if region:
        title_parts.append(region)
    if dept:
        title_parts.append(dept)
    if tag:
        title_parts.append(f"标签: {tag}")
    link = f"{base}/policy-radar/feed"
    if region:
        link += f"/{region}"
    if dept:
        link += f"/{dept}"
    xml = _build_rss_xml(
        title=" / ".join(title_parts),
        link=link,
        description=f"{' / '.join(title_parts)} - 共 {len(items)} 条",
        items=items,
        base_url=base,
    )
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/article/{policy_id}", response_class=Response)
async def get_article(policy_id: int):
    """单篇政策 - RSS 格式包装的 markdown。"""
    policies = await _query_policies(None, None, None, None, None, 500)
    target = next((p for p in policies if p["id"] == policy_id), None)
    if not target:
        raise HTTPException(404, f"政策 {policy_id} 不存在")
    base = "http://localhost:8000"
    md = html_to_clean_markdown(target["raw_content"])
    frontmatter = build_frontmatter(target)
    full_md = f"{frontmatter}\n\n# {target['title']}\n\n{md}\n\n---\n\n**原文链接**: {target['url']}\n**抓取时间**: {target['crawled_at']}\n**Markdown 链接**: {base}/policy-radar/markdown/{target['id']}\n"
    # 包装成 RSS
    desc = f'<pre style="white-space: pre-wrap; font-family: ui-monospace, monospace; background: #f5f5f5; padding: 1em; border-radius: 4px; font-size: 12px;">{escape(full_md)}</pre>'
    item = {
        "title": target["title"],
        "url": target["url"],
        "id": target["id"],
        "published_at": target["published_at"],
        "crawled_at": target["crawled_at"],
        "summary": target["summary"],
        "advisory": target["advisory"],
        "department": target["department"],
        "source_name": target["source_name"],
        "region": target["region"],
        "tags": target["tags"],
    }
    xml = _build_rss_xml(
        title=target["title"],
        link=target["url"],
        description=desc,
        items=[item],
        base_url=base,
    )
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@router.get("/markdown/{policy_id}", response_class=Response)
async def get_markdown(policy_id: int):
    """纯 Markdown 输出 - 知识库直接抓。"""
    policies = await _query_policies(None, None, None, None, None, 500)
    target = next((p for p in policies if p["id"] == policy_id), None)
    if not target:
        raise HTTPException(404, f"政策 {policy_id} 不存在")
    md = html_to_clean_markdown(target["raw_content"])
    frontmatter = build_frontmatter(target)
    base = "http://localhost:8000"
    full_md = (
        f"{frontmatter}\n\n"
        f"# {target['title']}\n\n"
        f"{md}\n\n"
        f"---\n\n"
        f"**原文链接**: {target['url']}\n"
        f"**抓取时间**: {target['crawled_at']}\n"
        f"**RSSHub**: {base}/policy-radar/article/{target['id']}\n"
    )
    return Response(
        content=full_md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="policy-{target["id"]}.md"'},
    )


@router.get("/opml", response_class=Response)
async def get_opml():
    """所有源 OPML 订阅列表。"""
    async with get_session() as session:
        stmt = select(PolicySource).where(PolicySource.enabled == True).order_by(PolicySource.region, PolicySource.name)
        result = await session.execute(stmt)
        sources = result.scalars().all()
    base = "http://localhost:8000"
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">', '<head>', '<title>政策雷达 - 全部 RSS 订阅</title>', '</head>', '<body>']
    by_region: dict[str, list] = {}
    for s in sources:
        by_region.setdefault(s.region or "other", []).append(s)
    for region in sorted(by_region.keys()):
        lines.append(f'<outline text="{escape(region or "其他")}" title="{escape(region or "其他")}">')
        for s in by_region[region]:
            feed_url = f"{base}/policy-radar/feed/{s.region or 'other'}"
            lines.append(
                f'<outline type="rss" text="{escape(s.name)}" title="{escape(s.name)}" '
                f'xmlUrl="{escape(feed_url)}" htmlUrl="{escape(s.url or "")}"/>'
            )
        lines.append("</outline>")
    lines.append("</body></opml>")
    return Response(content="\n".join(lines), media_type="text/xml; charset=utf-8")