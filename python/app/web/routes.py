"""Web 页面路由：MVP 触发页。

直接返回静态 HTML（不依赖 Jinja2 模板，避免 jinja2 缓存版本冲突）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
INDEX_HTML = TEMPLATES_DIR / "index.html"


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """触发页：4 按钮 + 1 列表 + 推送日志。"""
    html = INDEX_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=html)
