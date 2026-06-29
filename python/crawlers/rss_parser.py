"""RSS/Atom 解析器:从 RSSHub 路由输出 XML 抽 policy items。

不依赖第三方库(用 stdlib xml.etree.ElementTree)。
支持 RSS 2.0(RSSHub 默认)和 Atom(回退)。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


@dataclass
class RSSItem:
    """单条 RSS 条目。来自 RSS 2.0 的 <item> 或 Atom 的 <entry>。"""
    title: str
    link: str
    pub_date: Optional[str] = None
    description: Optional[str] = None
    guid: Optional[str] = None
    author: Optional[str] = None


def parse_rss(xml_text: str) -> list[RSSItem]:
    """解析 RSS 2.0 / Atom,返回 items 列表。失败返 []。

    RSSHub 默认输出 RSS 2.0;<item> 里含 title/link/pubDate/description/guid。
    部分路由走 Atom,<entry> 兼容。
    """
    if not xml_text or not xml_text.strip():
        return []
    items: list[RSSItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # 1) RSS 2.0: rss/channel/item
    for item_el in root.findall(".//item"):
        title = (item_el.findtext("title") or "").strip()
        link = (item_el.findtext("link") or "").strip()
        if not title and not link:
            continue
        items.append(
            RSSItem(
                title=title,
                link=link,
                pub_date=item_el.findtext("pubDate"),
                description=item_el.findtext("description"),
                guid=item_el.findtext("guid"),
                author=item_el.findtext("author") or item_el.findtext("dc:creator"),
            )
        )

    # 2) Atom 回退
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns):
            title = (entry.findtext("a:title", namespaces=ns) or "").strip()
            link = ""
            for l in entry.findall("a:link", namespaces=ns):
                href = l.get("href")
                if href:
                    link = href
                    break
            if not title and not link:
                continue
            pub = (
                entry.findtext("a:updated", namespaces=ns)
                or entry.findtext("a:published", namespaces=ns)
            )
            desc = (
                entry.findtext("a:summary", namespaces=ns)
                or entry.findtext("a:content", namespaces=ns)
            )
            items.append(
                RSSItem(
                    title=title,
                    link=link,
                    pub_date=pub,
                    description=desc,
                )
            )

    return items


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_description(html_or_text: Optional[str]) -> str:
    """RSS description 清理:去 HTML 标签 + 折叠空白 + 截 1000 字。

    爬到的 description 常含 HTML(<p><br/> 等)。入库前转纯文本。
    """
    if not html_or_text:
        return ""
    text = _TAG_RE.sub("", html_or_text)
    text = _WS_RE.sub(" ", text).strip()
    # 反转义常见实体
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&#39;", "'")
    )
    return text[:1000]


def extract_pub_date_iso(pub_date: Optional[str]) -> Optional[str]:
    """把 RSS pubDate(RFC822 如 'Mon, 29 Jun 2026 10:00:00 +0800')
    尽量转 ISO 8601,失败返 None。

    入 DB 的 published_at 用 datetime,parse_date 在 policy 入库前统一处理也可。
    这里先 try 解析,失败返 None 让 engine fallback 到爬取时间。
    """
    if not pub_date:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date)
        if dt is None:
            return None
        return dt.isoformat()
    except Exception:
        return None
