"""Web 页面路由：触发页 + Vue 3 管理后台。

直接返回静态 HTML（不依赖 Jinja2 模板，避免 jinja2 缓存版本冲突）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
INDEX_HTML = TEMPLATES_DIR / "index.html"
ADMIN_HTML = WEB_DIR / "admin.html"


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """触发页（MVP 简化版，Alpine.js + Tailwind）。"""
    html = INDEX_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/admin", response_class=HTMLResponse)
async def admin() -> HTMLResponse:
    """Vue 3 管理后台（5 tab）。"""
    html = ADMIN_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=html)
