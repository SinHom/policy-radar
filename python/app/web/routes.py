"""Web 页面路由：触发页 + Vue 3 管理后台。

直接返回静态 HTML（不依赖 Jinja2 模板，避免 jinja2 缓存版本冲突）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
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
    """Vue 3 SPA 入口(stage D 部署的 dist/index.html)。

    所有非具体路径(/admin /sources /policies 等)由 vue-router history 接管,
    命中下面 spa_fallback。/admin /min 老 admin.html 路由已删除,全部走 SPA。
    """
    html = FRONTEND_INDEX_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


# SPA fallback:vue-router history 模式需要的 fallback。
# 不匹配 /static 或 /assets 的路径都返回 index.html,前端 router 接管。
# 必须在所有具体路由之后声明。
# 政策顾问独立页面 - 秦皇岛驾驶舱（2026-07-20，2026-07-23 路由 /advisor -> /advisor-qhd 与抚顺版对称）
@router.get('/advisor-qhd', response_class=HTMLResponse)
async def advisor_qhd_page() -> HTMLResponse:
    """秦皇岛文旅政策驾驶舱页面，不走 Vue SPA。"""
    advisor_html = WEB_DIR / 'advisor.html'
    if not advisor_html.exists():
        raise HTTPException(status_code=404, detail='advisor.html not found')
    return HTMLResponse(content=advisor_html.read_text(encoding='utf-8'))


# 旧路径 /advisor -> /advisor-qhd 永久重定向（2026-07-23 路由改名后保留旧流量）
@router.get('/advisor', response_class=HTMLResponse)
async def advisor_legacy_redirect() -> RedirectResponse:
    return RedirectResponse(url='/advisor-qhd', status_code=301)


# 抚顺望花区法人政策驾驶舱（2026-07-21）：同功能，地区/数据改抚顺望花区
@router.get('/advisor-fushun', response_class=HTMLResponse)
async def advisor_fushun_page() -> HTMLResponse:
    """抚顺望花区法人政策驾驶舱页面，不走 Vue SPA。"""
    html = WEB_DIR / 'advisor-fushun.html'
    if not html.exists():
        raise HTTPException(status_code=404, detail='advisor-fushun.html not found')
    return HTMLResponse(content=html.read_text(encoding='utf-8'))


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
