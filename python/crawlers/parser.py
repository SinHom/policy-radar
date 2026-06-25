"""HTML 解析工具：BS4 + lxml。"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup, Tag

DATE_PATTERNS = [
    r"(\d{4})-(\d{1,2})-(\d{1,2})",  # 2026-06-24
    r"(\d{4})/(\d{1,2})/(\d{1,2})",  # 2026/06/24
    r"(\d{4})\.(\d{1,2})\.(\d{1,2})",  # 2026.06.24
    r"(\d{4})年(\d{1,2})月(\d{1,2})日",  # 2026年6月24日
]


def parse_html(html: str, parser: str = "lxml") -> BeautifulSoup:
    """解析 HTML。lxml 失败时回退 html.parser。"""
    try:
        return BeautifulSoup(html, parser)
    except Exception:
        return BeautifulSoup(html, "html.parser")


def extract_by_selector(
    soup: BeautifulSoup,
    selector: str,
    *,
    attr: Optional[str] = None,
    default: str = "",
) -> str:
    """用 CSS 选择器提取第一个匹配元素的文本或属性。

    selector 示例：
        "h1.article-title"        取文本
        "a"                       取 href
        "a::attr(href)"           取 href（显式）
    """
    if not selector:
        return default

    # 支持 ::attr(name) 语法
    attr_match = re.match(r"^(.+)::attr\(([^)]+)\)$", selector.strip())
    if attr_match:
        real_selector, attr_name = attr_match.group(1).strip(), attr_match.group(2).strip()
        el = soup.select_one(real_selector)
        if el is None:
            return default
        return el.get(attr_name, default) or default

    el = soup.select_one(selector)
    if el is None:
        return default

    if attr:
        return el.get(attr, default) or default

    # 默认 get_text(strip=True)
    return el.get_text(separator=" ", strip=True) if isinstance(el, Tag) else default


def extract_all(
    soup: BeautifulSoup, selector: str
) -> list[Tag]:
    """CSS 选择器匹配的所有元素。"""
    return soup.select(selector)


def extract_date(text: str) -> Optional[date]:
    """从文本里抽 YYYY-MM-DD 格式的日期。

    支持：
        - 2026-06-24
        - 2026/06/24
        - 2026.06.24
        - 2026年6月24日

    解析失败返回 None（MVP 阶段不写复杂推断）。
    """
    if not text:
        return None
    text = text.strip()
    for pat in DATE_PATTERNS:
        m = re.search(pat, text)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                return date(y, mo, d)
            except (ValueError, IndexError):
                continue
    return None


def extract_text(soup: BeautifulSoup, selector: str, max_len: int = 0) -> str:
    """提取文本（带 max_len 截断）。"""
    text = extract_by_selector(soup, selector)
    if max_len > 0 and len(text) > max_len:
        return text[:max_len]
    return text


def extract_href(soup: BeautifulSoup, selector: str) -> str:
    """提取 a 标签 href。"""
    return extract_by_selector(soup, selector, attr="href")
