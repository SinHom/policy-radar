"""HTTP 获取层：httpx（快）+ Playwright（JS 渲染）统一接口。

反爬策略：
- 随机 User-Agent（5 种桌面 UA 轮换）
- 真实浏览器请求头（Accept / Accept-Language / Referer）
- 随机请求间隔（按 spider 配置的 min/max）
- Playwright 模式隐藏 webdriver 痕迹
- 失败 3 次后跳过该 URL（避免无限重试）
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Optional

import ssl

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# 兼容部分政府站非常规椭圆曲线/证书（解决 OpenSSL3 BAD_ECPOINT）。
# 爬虫层忽略证书校验（与 Playwright ignore_https_errors 对齐），数据完整性靠内容校验。
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.set_ciphers("DEFAULT:@SECLEVEL=0")
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# 5 种真实桌面 User-Agent 轮换（Chrome 136 / Edge / Firefox / Safari）
# 优化参考.md P3: UA 升级到 Chrome 136, 防 WAF 标记老版本
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
]

# 5 种配套的 Sec-Ch-Ua 头（必须与 UA 主版本号一致）
SEC_CH_UA = [
    '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    '"Chromium";v="135", "Google Chrome";v="135", "Not.A/Brand";v="99"',
    '',  # Safari 不发 Sec-Ch-Ua
    '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
    '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
]

DEFAULT_USER_AGENT = USER_AGENTS[0]


def pick_user_agent() -> str:
    return random.choice(USER_AGENTS)


@dataclass
class FetchResult:
    """统一的获取结果。"""

    url: str
    html: str
    final_url: str  # 重定向后的 URL
    status_code: int
    encoding: str = "utf-8"


class Fetcher:
    """异步 fetcher，根据 render_js 自动选 httpx 或 Playwright。"""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        # 优化参考 P4: 默认间隔 3-5s 太短易被 WAF 识别, 提到 4-8s
        request_interval_min: float = 4.0,
        request_interval_max: float = 8.0,
        timeout: float = 60.0,
    ):
        self.user_agent = user_agent
        self.interval_min = request_interval_min
        self.interval_max = request_interval_max
        self.timeout = timeout

    async def _sleep(self) -> None:
        """随机请求间隔（反爬）。"""
        delay = random.uniform(self.interval_min, self.interval_max)
        await asyncio.sleep(delay)

    async def fetch(self, url: str, *, render_js: bool = False) -> FetchResult:
        """获取单个 URL。"""
        await self._sleep()
        # 每次随机换 UA（如果 user_agent 没显式指定）
        ua = self.user_agent if self.user_agent != DEFAULT_USER_AGENT else pick_user_agent()
        if render_js:
            return await self._fetch_playwright(url, ua)
        return await self._fetch_httpx(url, ua)

    async def _fetch_httpx(self, url: str, ua: str = None) -> FetchResult:
        ua = ua or self.user_agent
        # 优化参考 P3: 完整 Chrome 136 指纹头（防 WAF 标记老版本）
        # Sec-Ch-Ua 与 UA 主版本号必须一致
        ua_index = USER_AGENTS.index(ua) if ua in USER_AGENTS else 0
        sec_ch_ua = SEC_CH_UA[ua_index] if ua_index < len(SEC_CH_UA) else SEC_CH_UA[0]
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.baidu.com/",  # 政府站通常拒 google referer, baidu 通过率高
            "Cache-Control": "max-age=0",
            **({"Sec-Ch-Ua": sec_ch_ua} if sec_ch_ua else {}),
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        # 容器 IPv6 不可达,强制 IPv4 解析(否则 happy-eyeballs 优先 IPv6 卡 60s)
        # 仅对 HTTP 做 IP 替换;HTTPS 保留域名避免 SNI 不匹配导致 TLS 握手失败
        url_to_fetch = url
        try:
            import socket
            from urllib.parse import urlparse
            p = urlparse(url)
            host = p.hostname
            if host and p.scheme == "http":
                infos = socket.getaddrinfo(host, p.port or 80, socket.AF_INET, socket.SOCK_STREAM)
                if infos:
                    ip = infos[0][4][0]
                    url_to_fetch = f"{p.scheme}://{ip}{p.path}"
                    if p.query:
                        url_to_fetch += "?" + p.query
                    headers["Host"] = host
        except Exception:
            pass  # 解析失败 fallback 原 URL

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
            verify=SSL_CONTEXT,
        ) as client:
            resp = await client.get(url_to_fetch)
            resp.raise_for_status()
            encoding = resp.encoding or "utf-8"
            # 尝试用 apparent_encoding（特别是 GBK 老站）
            if encoding.lower() in ("iso-8859-1", "windows-1252"):
                try:
                    encoding = resp.apparent_encoding or encoding
                except Exception:
                    pass
            resp.encoding = encoding
            return FetchResult(
                url=url,
                html=resp.text,
                final_url=str(resp.url),
                status_code=resp.status_code,
                encoding=encoding,
            )

    async def _fetch_playwright(self, url: str, ua: str = None) -> FetchResult:
        ua = ua or self.user_agent
        # 第 9 轮 v5: QHD 域直接用代理 URL (launch proxy 在容器内不生效)
        _pw_url = url
        try:
            from urllib.parse import urlparse as _up3
            _h3 = _up3(url).hostname or ""
            if _h3.endswith("qhd.gov.cn") or _h3.endswith("hebei.gov.cn"):
                import urllib.parse as _u4
                _pw_url = f"http://172.18.0.4:8888/fetch?url={_u4.quote(url, safe='')}"
        except Exception:
            pass
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    user_agent=ua,
                    ignore_https_errors=True,
                    extra_http_headers={
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    },
                )
                page = await ctx.new_page()
                # 隐藏 webdriver 标志
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                resp = await page.goto(_pw_url, wait_until="commit", timeout=int(self.timeout * 1000))
                # 等网络空闲但最多 15 秒（避免卡在 networkidle）
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                # 第 9 轮 v6: kjj 等列表里的详情链接出现 (JS 异步渲染)
                try:
                    await page.wait_for_selector("a[href*='/home/details']", timeout=10000)
                except Exception:
                    pass
                html = await page.content()
                status = resp.status if resp else 200
                final_url = url  # 第 9 轮 v5: 用原始 URL 让 urljoin 正确
                return FetchResult(
                    url=url,
                    html=html,
                    final_url=final_url,
                    status_code=status,
                    encoding="utf-8",
                )
            finally:
                await browser.close()


# 全局默认实例
_default_fetcher: Optional[Fetcher] = None


def get_fetcher() -> Fetcher:
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = Fetcher()
    return _default_fetcher


async def fetch(url: str, *, render_js: bool = False) -> FetchResult:
    """便捷函数：用默认 fetcher 抓一次。"""
    return await get_fetcher().fetch(url, render_js=render_js)
