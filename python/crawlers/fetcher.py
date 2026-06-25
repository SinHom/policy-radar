"""HTTP 获取层：httpx（快）+ Playwright（JS 渲染）统一接口。"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Optional

import httpx
from playwright.async_api import async_playwright

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


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
        request_interval_min: float = 3.0,
        request_interval_max: float = 5.0,
        timeout: float = 30.0,
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
        if render_js:
            return await self._fetch_playwright(url)
        return await self._fetch_httpx(url)

    async def _fetch_httpx(self, url: str) -> FetchResult:
        async with httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
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

    async def _fetch_playwright(self, url: str) -> FetchResult:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    user_agent=self.user_agent,
                    ignore_https_errors=True,  # 绕过公司代理的 SSL 中断
                )
                page = await ctx.new_page()
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                # 等网络空闲但最多 5 秒（避免卡在 networkidle）
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                html = await page.content()
                status = resp.status if resp else 200
                final_url = page.url
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
