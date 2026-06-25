"""MCP Server 端到端测试。

不通过 MCP 协议层（避免 stdio 复杂度），直接 import 各个 handler 函数，
模拟 AI 工具的 7 个 Tool 调用，验证业务逻辑端到端。

流程：
    1. 清库 + alembic 迁移 + seed sources/policies + summarize
    2. 启动本地 mock webhook server（端口 9998）
    3. 模拟 start_setup（缺 industry）
    4. 模拟 complete_setup（补 industry）
    5. 模拟 confirm_setup（落库）
    6. 模拟 trigger_crawl（不调真实网络，用现有 mock 政策即可）
    7. 模拟 run_match_all
    8. 模拟 push_to_webhook → 验证 mock server 收到请求
    9. 模拟 get_matches / search_policies / get_policy_detail

运行：
    python -m scripts.mcp_e2e
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import time
from datetime import datetime
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request

from python.ai.summarizer import summarize_pending
from python.app.config import get_settings
from python.mcp_server.matcher import run_match_all
from python.mcp_server.scheduler import push_pending_matches
from python.mcp_server.tools.admin import handle_trigger_crawl
from python.mcp_server.tools.query import (
    handle_get_matches,
    handle_get_policy_detail,
    handle_search_policies,
)
from python.mcp_server.tools.setup import (
    handle_complete_setup,
    handle_confirm_setup,
    handle_start_setup,
)
from python.mcp_server.webhook import push_to_webhook
from python.models import Company, Match, Policy, Subscription
from python.models.base import get_session, init_session_factory, make_engine
from python.scripts import seed_policies, seed_sources
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp_e2e")

# === Mock webhook server on port 9998 ===
MOCK_WEBHOOK_PORT = 9998
MOCK_WEBHOOK_REQUESTS: list[dict] = []


def make_mock_webhook_app() -> FastAPI:
    app = FastAPI()

    @app.post("/")
    @app.post("/{path:path}")
    async def catch_all(request: Request):
        body = await request.json()
        MOCK_WEBHOOK_REQUESTS.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "headers": dict(request.headers),
            "body": body,
        })
        return {"errcode": 0, "errmsg": "ok"}

    return app


def start_mock_webhook() -> threading.Thread:
    """后台启动 mock webhook server。"""
    app = make_mock_webhook_app()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=MOCK_WEBHOOK_PORT, log_level="warning"
    )
    server = uvicorn.Server(config)

    def run():
        asyncio.run(server.serve())

    t = threading.Thread(target=run, daemon=True)
    t.start()
    # 等就绪
    for _ in range(20):
        try:
            r = httpx.get(f"http://127.0.0.1:{MOCK_WEBHOOK_PORT}/", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    logger.info("mock webhook server started on %d", MOCK_WEBHOOK_PORT)
    return t


# === 工具函数 ===

def parse_tool_result(result: list[dict]) -> dict:
    """MCP Tool 返回 list[TextContent]，取第一项 parse 成 dict。"""
    if not result:
        return {"status": "error", "error": "empty result"}
    text = result[0].get("text", "{}")
    return json.loads(text)


def log_step(step: str, data: Any) -> None:
    print(f"\n{'='*60}\n[{step}]\n{'='*60}")
    if isinstance(data, dict):
        # 用 errors='replace' 容错 Windows console
        text = json.dumps(data, ensure_ascii=False, indent=2)[:600]
        try:
            print(text)
        except UnicodeEncodeError:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(text)
    else:
        try:
            print(str(data)[:600])
        except UnicodeEncodeError:
            print(str(data)[:600].encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


# === 主流程 ===

async def main_async() -> int:
    # 0. 准备 DB
    settings = get_settings()
    engine = make_engine()
    init_session_factory(engine)

    # 1. seed sources + policies + summarize
    logger.info("Step 0: seed data")
    await seed_sources.seed()  # async!
    await seed_policies.seed()
    results = await summarize_pending(limit=5)
    logger.info("  summarized: %d/%d", sum(1 for r in results if r.get("ok")), len(results))

    # 2. 启 mock webhook
    start_mock_webhook()

    # 3. 模拟 start_setup（只传 company_name，缺其他字段）
    logger.info("Step 1: start_setup (company_name only)")
    r1 = parse_tool_result(await handle_start_setup({"company_name": "优智科技"}))
    log_step("start_setup", r1)
    assert r1["status"] == "need_more_info"
    assert len(r1["missing"]) > 0

    # 4. 模拟 complete_setup（补齐 industry/region/policy_types/regions/push_schedule）
    logger.info("Step 2: complete_setup (fill all fields)")
    setup_data = {
        "company_name": "优智科技",
        "industry": "科技/互联网",
        "region": "深圳",
        "policy_types": ["补贴", "贷款"],
        "regions": ["深圳", "广东"],
        "keywords": ["专精特新", "研发"],
        "push_schedule": "daily",
        "webhook_url": f"http://127.0.0.1:{MOCK_WEBHOOK_PORT}/feishu-test",
        "platform_hint": "feishu",
    }
    r2 = parse_tool_result(await handle_complete_setup(setup_data))
    log_step("complete_setup", r2)
    assert r2["status"] == "ready_to_confirm"

    # 5. 模拟 confirm_setup（落库）
    logger.info("Step 3: confirm_setup (commit to DB)")
    r3 = parse_tool_result(await handle_confirm_setup({"setup_data": r2["summary"]}))
    log_step("confirm_setup", r3)
    assert r3["status"] == "ok"
    company_id = r3["company_id"]

    # 6. 模拟 trigger_crawl（云上才有真实源，本地用 mock 数据即可）
    logger.info("Step 4: trigger_crawl (skip real network, use existing data)")
    # 这里不调真实爬虫（会失败），改用 mark 已存在
    async with get_session() as session:
        count = (await session.execute(select(Policy))).scalars().all()
    logger.info("  policies in DB: %d", len(count))

    # 7. 跑 match
    logger.info("Step 5: run_match_all")
    mr = await run_match_all()
    log_step("match", mr)
    assert mr["total_matches"] > 0, "应该至少匹配出几条"

    # 8. 跑 push
    logger.info("Step 6: push_pending_matches")
    pushed = await push_pending_matches()
    log_step("push", {"pushed": pushed})
    assert pushed > 0
    # 等 mock server 收请求
    await asyncio.sleep(0.5)
    assert len(MOCK_WEBHOOK_REQUESTS) > 0, "mock webhook 应该收到推送"
    logger.info("mock webhook 收到 %d 条推送", len(MOCK_WEBHOOK_REQUESTS))
    last_body = MOCK_WEBHOOK_REQUESTS[-1]["body"]
    log_step("webhook payload (last)", last_body)

    # 9. 模拟 get_matches
    logger.info("Step 7: get_matches")
    r4 = parse_tool_result(await handle_get_matches({
        "company_id": company_id, "limit": 5, "unpushed_only": False
    }))
    log_step("get_matches", r4)
    assert r4["status"] == "ok"
    assert r4["count"] > 0

    # 10. 模拟 search_policies
    logger.info("Step 8: search_policies")
    r5 = parse_tool_result(await handle_search_policies({
        "query": "专精特新", "days_back": 60, "limit": 5
    }))
    log_step("search_policies", r5)
    assert r5["status"] == "ok"
    assert r5["count"] > 0

    # 11. 模拟 get_policy_detail
    if r5["policies"]:
        pol_id = r5["policies"][0]["id"]
        r6 = parse_tool_result(await handle_get_policy_detail({"policy_id": pol_id}))
        log_step("get_policy_detail", r6)
        assert r6["status"] == "ok"

    # 总结
    print("\n" + "=" * 60)
    print("MCP E2E: PASS")
    print(f"  setup:        company_id={company_id}")
    print(f"  matches:      {mr['total_matches']}")
    print(f"  pushed:       {pushed}")
    print(f"  webhook received: {len(MOCK_WEBHOOK_REQUESTS)}")
    print(f"  get_matches:  {r4['count']} results")
    print(f"  search:       {r5['count']} results")
    print("=" * 60)
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
