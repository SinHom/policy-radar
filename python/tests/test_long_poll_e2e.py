"""测试 message_router long_poll_loop 端到端：起 mock iLink server + 真实跑 router 1 秒 + 注入消息 + 验证回复。"""

import asyncio
import json
import logging
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_e2e")

MOCK_PORT = 9996
MOCK_BOT_TOKEN = "mock-bot-token-e2e"

# 模拟 iLink：存 /sendmessage 收到的所有内容
SENT_MESSAGES: list[dict] = []
INJECT_QUEUE: list[dict] = []


def make_mock_ilink():
    app = FastAPI()

    @app.post("/get_bot_qrcode")
    def qr():
        return {"qrcode_url": "fake", "bot_token": MOCK_BOT_TOKEN}

    @app.post("/get_qrcode_status")
    def qr_status():
        return {"status": "ok", "bot_token": MOCK_BOT_TOKEN}

    @app.post("/getupdates")
    async def getupdates(request: Request):
        body = await request.json()
        cursor = body.get("get_updates_buf", "")
        msgs, INJECT_QUEUE[:] = list(INJECT_QUEUE), []
        return {"messages": msgs, "cursor": f"next-{time.time()}"}

    @app.post("/sendmessage")
    async def sendmsg(request: Request):
        body = await request.json()
        SENT_MESSAGES.append({
            "ts": time.time(),
            "context_token": body.get("context_token", ""),
            "content": body.get("message", {}).get("content", ""),
        })
        return {"status": "ok", "message_id": str(time.time())}

    @app.post("/_inject")
    async def inject(request: Request):
        body = await request.json()
        INJECT_QUEUE.append({
            "context_token": body.get("context_token", "mock-ctx"),
            "from_user": body.get("from_user", "mock-user"),
            "content": body.get("content", ""),
        })
        return {"status": "ok", "pending": len(INJECT_QUEUE)}

    return app


def start_mock():
    config = uvicorn.Config(make_mock_ilink(), host="127.0.0.1", port=MOCK_PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True).start()
    for _ in range(30):
        try:
            httpx.get(f"http://127.0.0.1:{MOCK_PORT}/get_bot_qrcode", timeout=1)
            return
        except Exception:
            time.sleep(0.2)


async def inject(content: str, ctx: str = "mock-ctx") -> None:
    async with httpx.AsyncClient() as c:
        await c.post(f"http://127.0.0.1:{MOCK_PORT}/_inject", json={"context_token": ctx, "content": content})


async def main() -> int:
    start_mock()
    await asyncio.sleep(0.5)

    # 准备 DB
    import os
    os.environ["MOCK_WECHAT_URL"] = f"http://127.0.0.1:{MOCK_PORT}"
    os.environ["MOCK_WECHAT_PORT"] = str(MOCK_PORT)
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONPATH"] = "python"
    os.environ["MINIMAX_API_KEY"] = "sk-fake-test-key"  # 让 LLM client 初始化不挂
    os.environ["ILINK_BASE_URL"] = f"http://127.0.0.1:{MOCK_PORT}"  # 用 mock iLink

    from python.app.config import get_settings
    from python.models import Company, Subscription
    from python.models.base import get_session, init_session_factory, make_engine
    from python.ai.summarizer import summarize_pending
    from python.scripts import seed_policies, seed_sources
    from python.mcp_server.matcher import run_match_all
    from python.wechat.ilink_client import save_token
    from python.wechat.message_router import long_poll_loop

    db_path = PROJECT_ROOT / "data" / "policy_radar.db"
    db_path.unlink(missing_ok=True)
    import subprocess
    subprocess.run(["alembic", "upgrade", "head"], cwd=PROJECT_ROOT, check=True, env={**os.environ, "PYTHONPATH": "python"})
    await seed_sources.seed()
    await seed_policies.seed()
    await summarize_pending(limit=5)

    settings = get_settings()
    init_session_factory(make_engine())

    # 注册订阅
    async with get_session() as session:
        comp = Company(name="E2E测试公司", industry="科技", region="深圳", tags=["高新技术"])
        session.add(comp)
        await session.flush()
        sub = Subscription(
            company_id=comp.id,
            types=["补贴", "贷款"],
            regions=["深圳"],
            keywords=[],
            push_schedule="daily",
            enabled=True,
        )
        session.add(sub)

    await run_match_all()

    # 保存 mock iLink token（这样 ilink_client 不会去真实微信）
    save_token(MOCK_BOT_TOKEN, user_id="test-user")

    # 注入测试消息
    print("\n=== long_poll_loop e2e ===")
    print("  [setup] inject 3 messages: bangzhu / 1 / zixun")
    # 先启 router，再注入（让 router 在第一次 long_poll 时能拿到）
    print("  [run] start long_poll_loop 1s (let router init ilink client)...")
    task = asyncio.create_task(long_poll_loop(poll_interval=1, long_poll_timeout=2))
    await asyncio.sleep(1)
    print("  [inject] inject messages")
    await inject("帮助", "e2e-ctx-1")
    await inject("1", "e2e-ctx-1")
    await inject("咨询", "e2e-ctx-2")
    # 再等 4 秒让 router 处理
    print("  [wait] wait 4s for router to process...")
    await asyncio.sleep(4)

    # 跑 router 5 秒（短 timeout 让长轮询快速返回）
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # 验证收到回复
    print(f"  [verify] 共收到 {len(SENT_MESSAGES)} 条回复:")
    expected = [
        ("e2e-ctx-1", "帮助"),
        ("e2e-ctx-1", "1"),
        ("e2e-ctx-2", "咨询"),
    ]
    ok = 0
    for ctx, hint_label in [("e2e-ctx-1", "bangzhu"), ("e2e-ctx-1", "1"), ("e2e-ctx-2", "zixun")]:
        matched = [m for m in SENT_MESSAGES if m["context_token"] == ctx]
        if matched:
            print(f"    [OK] {ctx} {hint_label} reply received ({len(matched[0]['content'])} chars)")
            ok += 1
        else:
            print(f"    [FAIL] {ctx} {hint_label} no reply")
    print(f"\n  passed {ok}/{len(expected)}")
    return 0 if ok == len(expected) else 1

    print(f"\n  通过 {ok}/{len(expected)}")
    return 0 if ok == len(expected) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
