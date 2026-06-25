"""爬虫模块：HTTP 获取 + 解析 + 去重 + 引擎调度。

每个政策源 = 一份 JSON 配置（spiders/*.json），不写代码。
"""

from python.crawlers.fetcher import Fetcher, fetch
from python.crawlers.parser import extract_by_selector, extract_date
from python.crawlers.dedup import is_duplicate
from python.crawlers.engine import crawl_source, run_crawler

__all__ = [
    "Fetcher",
    "fetch",
    "extract_by_selector",
    "extract_date",
    "is_duplicate",
    "crawl_source",
    "run_crawler",
]
