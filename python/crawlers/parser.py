"""HTML 解析工具：BS4 + lxml。"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

# 正文容器内这些标签在提取 HTML 片段时丢弃（导航/脚本/样式，与
# policy_radar.py::html_to_clean_markdown 的清理保持一致，但只在正文范围内）。
_CONTENT_STRIP_TAGS = ["script", "style", "nav", "footer", "header", "form", "button"]

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

    # 去掉 ::text 尾缀（BeautifulSoup 不支持伪元素）
    clean_selector = re.sub(r"::text$", "", selector.strip()).strip()

    el = soup.select_one(clean_selector)
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


def extract_content_html(
    soup: BeautifulSoup,
    selector: str,
    base_url: str = "",
    *,
    max_len: int = 100000,
    caption_images: bool = True,
) -> str:
    """提取正文容器的 HTML 片段（保留 <img>，补全相对 src 为绝对 URL）。

    与 extract_by_selector（纯文本）的区别：保留 img/a/table 等标签的 HTML，
    供下游 markdownify 转成 ``![](url)`` / 链接 / 表格，让 WeKnora 能抓取
    正文配图并按父 chunk 位置建立图片索引。

    selector 可逗号分隔多个备选（与 spider 配置 ``detail_selectors.content``
    一致，如 ``div#UCAP-CONTENT, .gxt-xilan-con, .article-content``）。

    若 ``caption_images=True`` 且配置了 MiniMax VL（MINIMAX_API_KEY 环境变量），
    会下载正文内每张绝对 URL 图片，调 VL 生成中文 caption，写进 ``<img alt=...>``。
    markdownify 后变成 ``![caption](url)``，caption 进入 chunk 文本被向量索引，
    实现"图片内容可检索"。VL 不可用或失败时静默降级（保留原 src 无 caption）。
    """
    if not selector:
        selector = "body"
    # 找第一个命中的容器（支持逗号分隔的备选选择器）
    container = None
    for sel in selector.split(","):
        sel = sel.strip()
        if not sel:
            continue
        container = soup.select_one(sel)
        if container is not None:
            break
    if container is None:
        container = soup.body or soup

    # 克隆后清理（不污染原 soup）：删 script/style/nav/footer 等
    node = container
    for tag_name in _CONTENT_STRIP_TAGS:
        for t in node.find_all(tag_name):
            t.decompose()

    # 补全图片相对路径为绝对 URL（政府站图片多为 /images/x 或 ../../x）
    if base_url:
        for img in node.find_all("img"):
            src = img.get("src", "")
            if src and not src.startswith(("data:", "http://", "https://")):
                img["src"] = urljoin(base_url, src)

    # 对正文图片生成 VLM caption（应用层 MiniMax-VL-01，绕过 WeKnora 内部 VLM）
    if caption_images:
        _caption_images(node, base_url)

    html = str(node)
    # 截断防超长（与原 extract_by_selector 的 100000 一致）
    if max_len > 0 and len(html) > max_len:
        html = html[:max_len]
    return html


def _caption_images(node, base_url: str) -> None:
    """对 node 内的绝对 URL 图片逐个调 VLM 生成 caption，写入 alt 属性。

    跳过 data: 内嵌、已有 alt（非空）的图，以及明显是 icon 的小图。
    VL 不可用（无 API key）时整个函数 no-op。
    """
    try:
        from python.ai.vlm_client import get_vlm_client
        vlm = get_vlm_client()
        if not vlm.enabled:
            return
    except Exception as e:  # 导入失败不阻塞抓取
        import logging
        logging.getLogger(__name__).debug("VLM unavailable, skip caption: %s", e)
        return

    import httpx as _httpx  # 局部导入，避免模块加载强依赖

    # 单页图片数量上限（防大量图耗尽 VL 配额 + 拖慢抓取）
    MAX_CAPTION_PER_PAGE = 5
    captioned = 0
    for img in node.find_all("img"):
        if captioned >= MAX_CAPTION_PER_PAGE:
            break
        src = img.get("src", "")
        # 只处理绝对 URL 图片（相对路径已被补全为绝对，data: 是内嵌图）
        if not src.startswith(("http://", "https://")):
            continue
        # 已有非空 alt 就不重复 caption
        if (img.get("alt") or "").strip():
            continue
        # 下载图片（带 Referer 绕 gov 站防盗链）
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                "Referer": base_url or src,
            }
            with _httpx.Client(timeout=15.0, follow_redirects=True, verify=False) as c:
                r = c.get(src, headers=headers)
            if r.status_code != 200 or not r.content:
                continue
            media = "image/jpeg"
            ct = r.headers.get("content-type", "")
            if "png" in ct:
                media = "image/png"
            elif "webp" in ct:
                media = "image/webp"
            elif src.lower().endswith(".png"):
                media = "image/png"
            caption = vlm.caption_image_bytes(r.content, media_type=media)
            if caption:
                img["alt"] = caption
                captioned += 1
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("caption_image failed for %s: %s", src[:80], e)
            continue
