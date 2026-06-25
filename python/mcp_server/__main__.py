"""MCP Server CLI 入口。

用法：
    python -m mcp_server --stdio          # 给 Claude Desktop
    python -m mcp_server --sse --port 3001  # 给远程 AI 工具

启动时自动：
    1. 初始化 DB session
    2. 启动 APScheduler 后台
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from python.app.config import get_settings
from python.models.base import init_session_factory, make_engine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Policy Radar MCP Server")
    p.add_argument("--stdio", action="store_true", help="stdio 模式（Claude Desktop）")
    p.add_argument("--sse", action="store_true", help="SSE/HTTP 模式（远程 AI 工具）")
    p.add_argument("--host", default="0.0.0.0", help="SSE 模式监听地址")
    p.add_argument("--port", "-p", type=int, default=3001, help="SSE 模式监听端口")
    p.add_argument("--no-scheduler", action="store_true", help="不启动定时任务（开发/测试用）")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def init_db() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url or None)
    init_session_factory(engine)
    logging.info("MCP Server: DB session initialized")


async def run_stdio() -> int:
    """stdio 模式：用 mcp.server.stdio.stdio_server 跑。"""
    from mcp.server.stdio import stdio_server
    from python.mcp_server.server import server as mcp_server

    init_db()

    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )
    return 0


async def run_sse(host: str, port: int) -> int:
    """SSE 模式：用 Starlette + SSE 跑（FastAPI 风格）。"""
    from mcp.server.sse import SseServerTransport
    from python.mcp_server.server import server as mcp_server
    from sse_starlette.sse import EventSourceResponse
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import Response

    init_db()

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )
        return Response()

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )

    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
    return 0


def main() -> int:
    args = parse_args()
    from python.app.logging_config import setup_logging
    setup_logging(
        level=("DEBUG" if args.verbose else None),
    )

    if not args.stdio and not args.sse:
        print("ERROR: 必须指定 --stdio 或 --sse", file=sys.stderr)
        return 1

    # 启 scheduler（stdio 模式也可起；sse 模式更应该起）
    if not args.no_scheduler:
        try:
            from python.mcp_server.scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            logging.warning("scheduler 启动失败: %s", e)

    if args.stdio:
        return asyncio.run(run_stdio())
    return asyncio.run(run_sse(args.host, args.port))


if __name__ == "__main__":
    sys.exit(main())
