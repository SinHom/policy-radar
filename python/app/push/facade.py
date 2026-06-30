"""多卡片批量推送 facade:对日报聚合等多卡片场景复用飞书/通用 webhook 通道。

各 channel 函数本身只处理单卡片,这里负责循环 N 张卡 + 错误聚合。
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Optional

import httpx

from python.app.push.dispatcher import PushResult

logger = logging.getLogger(__name__)


def _feishu_sign(secret: str, timestamp: int) -> str:
    import base64
    import hashlib
    import hmac
    string_to_sign = f"{timestamp}\n{secret}"
    return base64.b64encode(
        hmac.new(key=string_to_sign.encode("utf-8"), msg=b"", digestmod=hashlib.sha256).digest()
    ).decode()


def _feishu_signed_url(webhook_url: str, secret: str) -> str:
    ts = int(time.time())
    sign = _feishu_sign(secret, ts)
    sep = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{sep}timestamp={ts}&sign={urllib.parse.quote(sign, safe='')}"


async def push_daily_cards(
    cards: list[dict],
    channel: str,
    config: dict,
    *,
    company_name: Optional[str] = None,
) -> dict:
    """循环发送多张卡片到指定 channel。返回 {ok, sent, errors, first_error}。"""
    if not cards:
        return {"ok": False, "error": "no cards"}

    if channel == "feishu":
        webhook_url = config.get("webhook_url")
        secret = config.get("secret")
        if not webhook_url:
            return {"ok": False, "error": "feishu 未配置 webhook_url"}
        target_url = _feishu_signed_url(webhook_url, secret) if secret else webhook_url

        sent = 0
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            for i, card in enumerate(cards, 1):
                try:
                    r = await client.post(target_url, json=card)
                    r.raise_for_status()
                    data = r.json()
                    code = data.get("code") or data.get("StatusCode") or 0
                    if code != 0:
                        errors.append(
                            f"card {i}: {data.get('msg') or data.get('Message') or f'code={code}'}"
                        )
                    else:
                        sent += 1
                except Exception as e:
                    errors.append(f"card {i}: {str(e)[:120]}")
        return {
            "ok": sent == len(cards),
            "sent": sent,
            "total": len(cards),
            "errors": errors,
            "channel": "feishu",
            "target": webhook_url[:80],
        }

    if channel == "webhook":
        # 通用 webhook:每张卡发一个 POST
        webhook_url = config.get("webhook_url")
        secret = config.get("secret")
        if not webhook_url:
            return {"ok": False, "error": "webhook 未配置 webhook_url"}
        import hashlib
        import hmac
        import json
        sent = 0
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            for i, card in enumerate(cards, 1):
                try:
                    body = json.dumps({"daily_report": True, "card": card, "company": company_name},
                                       ensure_ascii=False).encode("utf-8")
                    headers = {"Content-Type": "application/json"}
                    if secret:
                        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                        headers["X-Policy-Radar-Signature"] = f"sha256={sig}"
                    r = await client.post(webhook_url, content=body, headers=headers)
                    r.raise_for_status()
                    sent += 1
                except Exception as e:
                    errors.append(f"card {i}: {str(e)[:120]}")
        return {
            "ok": sent == len(cards),
            "sent": sent,
            "total": len(cards),
            "errors": errors,
            "channel": "webhook",
            "target": webhook_url[:80],
        }

    return {"ok": False, "error": f"daily_report 不支持 channel={channel} (目前只支持 feishu/webhook)"}
