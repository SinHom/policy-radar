"""Web 页面路由：触发页 + Vue 3 管理后台。

直接返回静态 HTML（不依赖 Jinja2 模板，避免 jinja2 缓存版本冲突）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter()

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
INDEX_HTML = TEMPLATES_DIR / "index.html"
ADMIN_HTML = WEB_DIR / "admin.html"

# Vue 3 SPA build(由 stage D 部署:前端 dist/ → server /opt/policy-radar/frontend_dist → docker cp 至此)
FRONTEND_DIST = WEB_DIR / "frontend_dist"
FRONTEND_INDEX_HTML = FRONTEND_DIST / "index.html"


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Vue 3 SPA 入口(stage D 部署的 dist/index.html)。"""
    html = FRONTEND_INDEX_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/admin", response_class=HTMLResponse)
async def admin() -> HTMLResponse:
    """Vue 3 管理后台（5 tab,老 admin.html 留作回退）。"""
    html = ADMIN_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/min", response_class=HTMLResponse)
async def min_test() -> HTMLResponse:
    """最小 Vue 测试页（排查白屏用）。"""
    return HTMLResponse(content=(WEB_DIR / "min.html").read_text(encoding="utf-8"))


# SPA fallback:vue-router history 模式需要的 fallback。
# 不匹配 /static 或 /assets 的路径都返回 index.html,前端 router 接管。
# 必须在所有具体路由之后声明。
@router.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str) -> HTMLResponse:
    """SPA fallback:所有未匹配的 path 返回 dist/index.html。

    前提:前端 vue-router 接管 history 路由(/sources /policies 等)。
    /api/* 和 /static/* /assets/* 由它们的 router / mount 处理,
    web_router 不会收到(在路由匹配前被 api_router/static mount 拦截)。
    """
    if not FRONTEND_INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail="frontend dist not deployed")
    return HTMLResponse(content=FRONTEND_INDEX_HTML.read_text(encoding="utf-8"))


# 静态资源（Vue/axios/Tailwind 本地化）：/static/vendor/xxx.js
static_app = StaticFiles(directory=str(STATIC_DIR))

# Vue 3 SPA build 静态资源(css/js bundle):/assets/index-xxx.css|js
frontend_assets_app = StaticFiles(directory=str(FRONTEND_DIST / "assets"))
