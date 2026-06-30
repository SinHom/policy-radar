"""FastAPI 主入口。"""

from __future__ import annotations

import asyncio
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
    """启动时初始化 DB + 后台 scheduler 定时爬取。"""
    settings = get_settings()
    engine = make_engine(settings.database_url or None)
    init_session_factory(engine)
    logger.info("Policy Radar started on port %d", settings.app_port)

    # ============== 后台定时爬取 ==============
    # interval=0 关闭 scheduler(测试用)
    interval = getattr(settings, "crawl_interval_seconds", 3600)

    async def _crawl_tick() -> None:
        """单次爬取(捕获异常,不让 scheduler 死)."""
        try:
            from python.crawlers.engine import run_crawler
            logger.info("Scheduler: tick 开始,爬取所有 enabled 源")
            results = await run_crawler()
            total_new = sum(r.new_crawled for r in results)
            logger.info(
                "Scheduler: tick 完成,共 %d 源, 新增 %d 条",
                len(results),
                total_new,
            )
        except Exception as e:
            logger.exception("Scheduler tick 失败: %s", e)

    async def _scheduler_loop() -> None:
        """循环:启动 30s 后跑第一次,之后每 interval 跑一次。"""
        await asyncio.sleep(30)  # 给容器启动 30s 预热(避免 healthcheck 期间跑)
        while True:
            await _crawl_tick()
            if interval <= 0:
                logger.info("Scheduler: interval=0, 停止")
                return
            await asyncio.sleep(interval)

    # ============== 日报推送 scheduler ==============
    # 早 9:00 / 午 12:00 / 晚 20:00(北京时间 = UTC+8,服务器时区是 UTC → 北京时间 9:00 = UTC 1:00)
    # 用 asyncio 简单模拟 cron:循环检查当前分钟/小时,匹配则触发
    async def _daily_report_loop() -> None:
        """每日 3 个时段对所有 enabled+feishu channel subscription 推日报聚合卡片。"""
        # UTC 1:00 = 北京 9:00 / UTC 4:00 = 北京 12:00 / UTC 12:00 = 北京 20:00
        slot_hour_map = {1: "早间", 4: "午间", 12: "晚间"}
        last_triggered: dict[str, str] = {}  # slot → "YYYY-MM-DD HH:MM" 防重复
        from datetime import datetime
        await asyncio.sleep(60)  # 启动后 1min 再检查
        while True:
            now = datetime.utcnow()
            slot = slot_hour_map.get(now.hour)
            if slot:
                key = f"{now.strftime('%Y-%m-%d')}-{slot}"
                if last_triggered.get(key) != now.strftime("%H:%M"):
                    try:
                        logger.info("Daily report: 触发 slot=%s", slot)
                        from python.app.push.daily_report_v2 import run_daily_report_all_subs
                        sent = await run_daily_report_all_subs(slot=slot)
                        logger.info("Daily report: %s 推送完成 sent=%d", slot, sent)
                        last_triggered[key] = now.strftime("%H:%M")
                    except Exception as e:
                        logger.exception("Daily report %s 失败: %s", slot, e)
            # 每 60 秒检查一次
            await asyncio.sleep(60)

    scheduler_task: asyncio.Task | None = None
    daily_task: asyncio.Task | None = None
    if interval > 0:
        scheduler_task = asyncio.create_task(_scheduler_loop())
        daily_task = asyncio.create_task(_daily_report_loop())
        logger.info("后台 scheduler 启动, interval=%ds + 日报 scheduler", interval)
    else:
        logger.info("crawl_interval_seconds=0, scheduler 关闭")

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        if daily_task is not None:
            daily_task.cancel()
            try:
                await daily_task
            except asyncio.CancelledError:
                pass
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
        BodySizeLimitMiddleware, RateLimitMiddleware, AuditMiddleware,
    )
    # 最后加的最先执行（middleware stack 是 LIFO）
    # 实际请求流：SafeError → SecurityHeaders → BodySize → RateLimit → Audit → route
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=1 * 1024 * 1024)  # 1MB
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SafeErrorMiddleware)

    # 静态资源 mount 在前(优先于 router 匹配,避免 SPA fallback 抢 assets)
    from python.app.web.routes import static_app, frontend_assets_app
    app.mount("/static", static_app, name="static")
    app.mount("/assets", frontend_assets_app, name="frontend_assets")

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
