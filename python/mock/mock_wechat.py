"""Mock 微信 iLink 服务。

参考 iLink 协议（来自 groovy-swinging-rain.md），实现以下端点：
  GET  /get_bot_qrcode   → 返回 fake qrcode + bot_token
  POST /getupdates       → 长轮询，返回 PENDING_MESSAGES 队列里塞的消息
  POST /sendmessage      → 收推送内容，print + 追加到 data/pushed_messages.log
  POST /_inject          → 测试用：往 PENDING_MESSAGES 塞消息

启动：
    python -m mock
    python -m mock --port 9999 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# 路径：项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_FILE = PROJECT_ROOT / "data" / "pushed_messages.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Mock WeChat iLink", version="0.1.0")

# 模拟的待发消息队列（注入用）
PENDING_MESSAGES: list[dict] = []
_LOCK = threading.Lock()

MOCK_BOT_TOKEN = "mock-bot-token-fake-12345"


@app.get("/")
def root():
    return {
        "service": "Mock WeChat iLink",
        "endpoints": [
            "GET  /get_bot_qrcode",
            "POST /getupdates",
            "POST /sendmessage",
            "POST /_inject",
        ],
        "log_file": str(LOG_FILE),
    }


@app.get("/get_bot_qrcode")
def get_bot_qrcode():
    """模拟扫码登录：返回 fake qrcode_url + bot_token。"""
    return {
        "qrcode_url": "https://fake.qrcode/ilink-mock.png",
        "bot_token": MOCK_BOT_TOKEN,
        "expires_in": 1800,
    }


@app.post("/getupdates")
async def getupdates(request: Request):
    """长轮询：返回 PENDING_MESSAGES 队列里的所有消息（消费式）。"""
    cursor = ""
    try:
        body = await request.json()
        cursor = body.get("get_updates_buf", "")
    except Exception:
        pass
    with _LOCK:
        msgs, PENDING_MESSAGES[:] = list(PENDING_MESSAGES), []
    return {
        "messages": msgs,
        "cursor": f"next-{uuid.uuid4().hex[:8]}",
    }


@app.post("/sendmessage")
async def sendmessage(request: Request):
    """收推送：把内容 print + 追加到 log 文件。"""
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse({"status": "error", "error": f"invalid json: {e}"}, status_code=400)

    context_token = body.get("context_token", "")
    message = body.get("message", {})
    msg_type = message.get("message_type", 1)
    content = message.get("content", "")

    ts = datetime.now().isoformat(timespec="seconds")
    short_token = context_token[:12] if context_token else "-"
    log_line = f"[{ts}] target={short_token:12s} type={msg_type} | {content}\n"

    # 写文件
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(log_line)

    # 控制台 print（Windows console GBK 不能 print emoji，用 replace 容错）
    try:
        print(f"\n{'='*60}")
        print(f"[MOCK-PUSH] {ts}")
        print(f"  target: {short_token}")
        print(f"  type:   {msg_type}")
        print(f"  content:")
        for line in content.splitlines():
            print(f"    {line}")
        print(f"{'='*60}\n", flush=True)
    except UnicodeEncodeError:
        # emoji 触发 Windows console 编码失败，用 errors='replace' 重新输出
        import sys
        safe = lambda s: s.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8', errors='replace')
        print(f"\n{'='*60}", flush=True)
        print(safe(f"[MOCK-PUSH] {ts}"), flush=True)
        print(safe(f"  target: {short_token}"), flush=True)
        print(safe(f"  type:   {msg_type}"), flush=True)
        print(safe("  content:"), flush=True)
        for line in content.splitlines():
            print(safe(f"    {line}"), flush=True)
        print(f"{'='*60}\n", flush=True)

    return {
        "status": "ok",
        "message_id": uuid.uuid4().hex,
        "timestamp": ts,
    }


@app.post("/_inject")
async def inject_message(request: Request):
    """测试用：往 PENDING_MESSAGES 队列塞消息。"""
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse({"status": "error", "error": f"invalid json: {e}"}, status_code=400)
    with _LOCK:
        PENDING_MESSAGES.append({
            "context_token": body.get("context_token", "mock-ctx"),
            "from_user": body.get("from_user", "mock-user"),
            "content": body.get("content", ""),
            "timestamp": datetime.now().isoformat(),
        })
    return {"status": "ok", "pending_count": len(PENDING_MESSAGES)}


def start_server(host: str = "0.0.0.0", port: int = 9999):
    import uvicorn
    print(f"[mock-wechat] starting on {host}:{port}")
    print(f"[mock-wechat] log file: {LOG_FILE}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mock WeChat iLink server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", "-p", type=int, default=int(os.environ.get("MOCK_WECHAT_PORT", "9999")))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    start_server(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
