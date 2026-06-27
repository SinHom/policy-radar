"""FastAPI 主入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from python.app.api.routes import router as api_router
from python.app.api.health import router as health_router
from python.app.api.dashboard import router as dashboard_router
from python.app.api.audit import router as audit_router
from python.app.api.auth import router as auth_router
from python.app.api.companies import router as companies_router
from python.app.api.llm_admin import router as llm_admin_router
from python.app.api.policies_admin import router as policies_admin_router
from python.app.api.sources_admin import router as sources_admin_router
from python.app.api.subscriptions import router as subs_router
from python.app.config import get_settings
from python.app.logging_config import setup_logging
from python.app.web.routes import router as web_router
from python.models.base import init_session_factory, make_engine

# 启动时初始化 logging
setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB session 工厂。"""
    settings = get_settings()
    engine = make_engine(settings.database_url or None)
    init_session_factory(engine)
    logger.info("Policy Radar started on port %d", settings.app_port)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Policy Radar MVP",
        version="0.1.0",
        lifespan=lifespan,
    )
    # === 安全中间件（顺序很重要：先外后内） ===
    from python.app.middleware import (
        SafeErrorMiddleware, SecurityHeadersMiddleware,
        BodySizeLimitMiddleware, RateLimitMiddleware,
    )
    # 最后加的最先执行（middleware stack 是 LIFO）
    # 实际请求流：SafeError → SecurityHeaders → BodySize → RateLimit → route
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=1 * 1024 * 1024)  # 1MB
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SafeErrorMiddleware)

    app.include_router(api_router, prefix="/api", tags=["api"])
    # auth_router 自身已带 prefix="/api/auth"，不要重复加
    app.include_router(auth_router, tags=["auth"])
    # subs_router 自身已带 prefix="/api/subscriptions"，不要重复加
    app.include_router(subs_router, tags=["subscriptions"])
    # companies_router 自身已带 prefix="/api/companies"
    app.include_router(companies_router, tags=["companies"])
    # policies_admin_router 自身已带 prefix="/api/policies"
    # 注意：会跟 api_router 里的 /api/policies 冲突（不同方法/不同路径），FastAPI 会按更具体的优先
    app.include_router(policies_admin_router, tags=["policies-admin"])
    # sources_admin_router 自身已带 prefix="/api/sources"
    app.include_router(sources_admin_router, tags=["sources-admin"])
    # llm_admin_router（路径：/api/llm/usage, /api/config/llm）
    app.include_router(llm_admin_router, tags=["llm-admin"])
    # audit_router（路径：/api/audit/logs, /api/audit/stats）
    app.include_router(audit_router, tags=["audit"])
    app.include_router(health_router, tags=["ops"])
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
    app.include_router(web_router, tags=["web"])
    # 静态资源（Vue/axios/Tailwind）
    from python.app.web.routes import static_app
    app.mount("/static", static_app, name="static")
    return app


app = create_app()


def main() -> int:
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "python.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
