"""通用 webhook 通道：向任意 URL POST JSON（可选 HMAC 签名）。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import httpx

from python.app.push.dispatcher import PushContent, PushResult, register

logger = logging.getLogger(__name__)


@register("webhook")
async def send(content: PushContent, config: dict) -> PushResult:
    """推送到任意 webhook URL。body 是 JSON。"""
    webhook_url: Optional[str] = config.get("webhook_url")
    secret: Optional[str] = config.get("secret")

    if not webhook_url:
        return PushResult(ok=False, channel="webhook", target="-",
                          error="webhook 通道未配置 webhook_url")

    body = {
        "policy_id": content.policy_id,
        "title": content.title,
        "summary": content.summary,
        "summary_type": content.summary_type,
        "amount": content.amount,
        "deadline": content.deadline,
        "url": content.url,
        "source_id": content.source_id,
        "company_id": content.company_id,
        "company_name": content.company_name,
        "pushed_at": time.time(),
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        headers["X-Policy-Radar-Signature"] = f"sha256={sig}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(webhook_url, content=body_bytes, headers=headers)
            r.raise_for_status()
    except Exception as e:
        return PushResult(ok=False, channel="webhook", target=webhook_url[:60],
                          error=str(e)[:300])

    return PushResult(ok=True, channel="webhook", target=webhook_url[:80])
