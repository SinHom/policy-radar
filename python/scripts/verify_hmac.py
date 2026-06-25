"""验证 HMAC 签名：起 mock server 记录 headers，触发 push，检查 header 是否带签名。"""

import asyncio
import json
import logging
import sys
import threading
import time

import httpx
import uvicorn
from fastapi import FastAPI, Request

from python.app.config import get_settings
from python.models import Company, Match, Policy, Subscription
from python.models.base import get_session, init_session_factory, make_engine
from python.mcp_server.webhook import push_to_webhook
from python.ai.summarizer import summarize_pending
from python.scripts import seed_policies, seed_sources
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_hmac")

RECEIVED: list[dict] = []

app = FastAPI()


@app.post("/{path:path}")
@app.post("/")
async def catch_all(request: Request):
    body = await request.body()
    RECEIVED.append({
        "headers": dict(request.headers),
        "body": body.decode("utf-8", errors="replace"),
    })
    return {"errcode": 0, "errmsg": "ok"}


def start_mock():
    config = uvicorn.Config(app, host="127.0.0.1", port=9999, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True).start()
    for _ in range(20):
        try:
            httpx.get("http://127.0.0.1:9999/", timeout=1)
            return
        except Exception:
            time.sleep(0.2)


async def main():
    settings = get_settings()
    engine = make_engine()
    init_session_factory(engine)
    start_mock()

    # 准备数据
    await seed_sources.seed()
    await seed_policies.seed()
    await summarize_pending(limit=5)

    # 设一个带 secret 的 subscription
    async with get_session() as session:
        comp = Company(name="HMAC测试公司", industry="科技", region="深圳", tags=["高新技术"])
        session.add(comp)
        await session.flush()
        sub = Subscription(
            company_id=comp.id,
            types=["补贴", "贷款"],
            regions=["深圳"],
            keywords=["专精特新"],
            push_schedule="daily",
            webhook_url="http://127.0.0.1:9999/hmac-test",
            webhook_secret="my-shared-secret-12345",
            platform_hint="generic",
            enabled=True,
        )
        session.add(sub)
        await session.flush()
        sub_id = sub.id
        comp_id = comp.id
        # 拿一些 policy
        pols = list((await session.execute(select(Policy).limit(2))).scalars().all())
        for p in pols:
            session.add(Match(
                subscription_id=sub_id,
                policy_id=p.id,
                score=80,
                reasons=["测试"],
                pushed=False,
            ))

    # 触发 push
    async with get_session() as session:
        stmt = (
            select(Subscription)
            .where(Subscription.id == sub_id)
            .options(selectinload(Subscription.company))
        )
        sub = (await session.execute(stmt)).scalar_one()
        stmt2 = (
            select(Match, Policy)
            .join(Policy, Match.policy_id == Policy.id)
            .where(Match.subscription_id == sub_id)
            .where(Match.pushed.is_(False))
        )
        rows = list((await session.execute(stmt2)).all())

        result = await push_to_webhook(sub, rows)

    await asyncio.sleep(0.3)

    print("\n" + "=" * 60)
    print("HMAC 验证")
    print("=" * 60)
    print(f"push result: {result}")
    print(f"RECEIVED count: {len(RECEIVED)}")
    if RECEIVED:
        rec = RECEIVED[0]
        print(f"\nrequest headers:")
        for k, v in rec["headers"].items():
            if k.lower().startswith("x-policy") or k.lower() == "content-type":
                print(f"  {k}: {v[:100]}")
        sig = rec["headers"].get("x-policy-radar-signature", "")
        body = rec["body"]
        # 验证签名
        import hashlib, hmac
        expected = "sha256=" + hmac.new(b"my-shared-secret-12345", body.encode("utf-8"), hashlib.sha256).hexdigest()
        print(f"\nreceived signature: {sig}")
        print(f"expected signature:  {expected}")
        print(f"signature match: {sig == expected}")

        if sig and sig == expected:
            print("\nHMAC 签名验证: PASS")
        else:
            print("\nHMAC 签名验证: FAIL")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
