"""测试 message_router：本地 mock iLink server 验证命令解析 + 回复。"""

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

# 让 venv 加载到
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_router")

# 启动 mock iLink
MOCK_PORT = 9997
PENDING: list[dict] = []
TOKEN = "mock-bot-token-test"


def make_mock_ilink():
    app = FastAPI()

    @app.post("/get_bot_qrcode")
    def qr():
        return {"qrcode_url": "fake", "bot_token": TOKEN}

    @app.post("/get_qrcode_status")
    def qr_status():
        return {"status": "ok", "bot_token": TOKEN}

    @app.post("/getupdates")
    async def getupdates(request: Request):
        body = await request.json()
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return {"error": "unauthorized"}, 401
        msgs, PENDING[:] = list(PENDING), []
        return {"messages": msgs, "cursor": f"next-{time.time()}"}

    @app.post("/sendmessage")
    async def sendmsg(request: Request):
        body = await request.json()
        PENDING.append({"received": body})
        return {"status": "ok", "message_id": str(time.time())}

    @app.post("/_inject")
    async def inject(request: Request):
        body = await request.json()
        PENDING.append({
            "context_token": body.get("context_token", "mock-ctx"),
            "from_user": body.get("from_user", "mock-user"),
            "content": body.get("content", ""),
        })
        return {"status": "ok", "pending": len(PENDING)}

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


async def inject_msg(content: str, ctx: str = "mock-ctx") -> None:
    """注入消息到 mock iLink。"""
    async with httpx.AsyncClient() as c:
        await c.post(f"http://127.0.0.1:{MOCK_PORT}/_inject", json={"context_token": ctx, "content": content})


async def main() -> int:
    start_mock()
    await asyncio.sleep(0.5)

    # 准备数据：注册一个订阅 + 创建一条匹配
    sys.path.insert(0, str(PROJECT_ROOT))
    from python.app.config import get_settings
    from python.models import Company, Match, Policy, Subscription
    from python.models.base import get_session, init_session_factory, make_engine
    from python.ai.summarizer import summarize_pending
    from python.scripts import seed_policies, seed_sources

    # 设环境
    import os
    os.environ["MOCK_WECHAT_URL"] = f"http://127.0.0.1:{MOCK_PORT}"
    os.environ["MOCK_WECHAT_PORT"] = str(MOCK_PORT)
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONPATH"] = "python"

    # 重置 DB
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
        comp = Company(name="iLink测试", industry="科技", region="深圳", tags=["高新技术"])
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
        await session.flush()
        comp_id = comp.id

    # 跑 match
    from python.mcp_server.matcher import run_match_all
    await run_match_all()

    # 跑 router（短轮询 1 次）
    from python.wechat.message_router import handle_command

    # 先测：未注册用户（MVP 简化逻辑：单租户 → 临时 disable 所有 sub 测"无订阅"）
    from python.models import Subscription as _Sub
    from sqlalchemy import update, select
    async with get_session() as session:
        result = await session.execute(update(_Sub).values(enabled=False))
        await session.commit()
        print(f"  [debug] update subs: {result.rowcount} rows affected")
    async with get_session() as session:
        rows = (await session.execute(select(_Sub))).scalars().all()
        print(f"  [debug] subs in DB: {len(rows)}, enabled: {[s.enabled for s in rows]}")
    reply = await handle_command("帮助", "no-such-user")
    assert "还没有订阅" in reply, f"无订阅用户应提示订阅，got: {reply[:80]}"
    print(f"  [无订阅用户] '帮助' → '{reply[:30]}...' OK")
    # 重新启用
    async with get_session() as session:
        await session.execute(update(_Sub).values(enabled=True))
        await session.commit()

    # 再测：已注册用户的各种命令
    test_cases = [
        ("帮助", "help"),
        ("1", "detail_num"),
        ("详情 1", "detail_id"),
        ("咨询", "consult"),
        ("暂停", "pause"),
        ("恢复", "resume"),
        ("你好", "chat"),
    ]
    print("\n=== 路由命令测试 ===")
    ok = 1  # 未注册用户已经过了
    for text, expected_cmd in test_cases:
        try:
            reply = await handle_command(text, "mock-ctx")
            print(f"  [{expected_cmd}] '{text}' → {len(reply)} 字符")
            ok += 1
        except Exception as e:
            print(f"  [FAIL] '{text}' → {e}")

    print(f"\n  通过 {ok}/{len(test_cases) + 1}")
    return 0 if ok == len(test_cases) + 1 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
