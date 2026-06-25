"""Webhook 推送：根据 platform_hint 把 matches 格式化成对应平台的消息体，POST 到 webhook_url。

支持平台：
- generic:  通用 JSON
- feishu:   飞书机器人卡片
- wecom:    企业微信 Markdown

鉴权：
- 如果 subscription.webhook_secret 非空，POST 时加 header
  `X-Policy-Radar-Signature: sha256=<hex(hmac_sha256(secret, json_body))>`
- 接收方用同样 secret 验证 body 未被篡改
- 飞书/企微 webhook 本身不能验签（公开 URL），但用户自建中转站能验

调用方：scheduler.py / push.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from python.models import Match, Policy, Subscription

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Policy-Radar-Signature"

# 平台识别
PLATFORM_GENERIC = "generic"
PLATFORM_FEISHU = "feishu"
PLATFORM_WECOM = "wecom"
VALID_PLATFORMS = {PLATFORM_GENERIC, PLATFORM_FEISHU, PLATFORM_WECOM}


def detect_platform(url: str) -> str:
    """从 webhook URL 自动识别平台。"""
    if "open.feishu.cn" in url or "open.larksuite.com" in url:
        return PLATFORM_FEISHU
    if "qyapi.weixin.qq.com" in url:
        return PLATFORM_WECOM
    return PLATFORM_GENERIC


def _format_match_for_payload(m: Match, pol: Policy) -> dict:
    """把一条 Match + Policy 格式化成统一结构的 dict。"""
    return {
        "policy_id": pol.id,
        "title": pol.title,
        "type": pol.summary_type or "其他",
        "summary": pol.summary_text or "",
        "amount": (pol.summary_data or {}).get("amount"),
        "deadline": (pol.summary_data or {}).get("deadline"),
        "score": m.score,
        "reasons": m.reasons or [],
    }


def _format_payload_generic(company_name: str, matches_payload: list[dict]) -> dict:
    return {
        "event_type": "policy_matches",
        "company": {"name": company_name},
        "matches": matches_payload,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _format_payload_feishu(company_name: str, matches_payload: list[dict]) -> dict:
    """飞书自定义机器人卡片。"""
    if not matches_payload:
        title = f"📡 政策雷达 · {company_name} · 暂无新匹配"
        elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "今天没有匹配到新政策。"}}]
    else:
        n = len(matches_payload)
        title = f"📡 政策雷达 · {company_name} · 今日 {n} 条匹配"
        elements = []
        for i, m in enumerate(matches_payload, 1):
            # 颜色按 score
            if m["score"] >= 80:
                color = "🟢"
            elif m["score"] >= 60:
                color = "🔵"
            else:
                color = "🟣"
            amount_line = f"\n💰 {m['amount']}" if m.get("amount") else ""
            deadline_line = f" ⏰ 截止 {m['deadline']}" if m.get("deadline") else ""
            text = f"**{color} {m['score']}% | {m['type']}**\n**[{m['title']}]({m.get('detail_url','')})**{amount_line}{deadline_line}"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": text}})
            if i < n:
                elements.append({"tag": "hr"})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }


def _format_payload_wecom(company_name: str, matches_payload: list[dict]) -> dict:
    """企业微信 Markdown。"""
    if not matches_payload:
        content = f"## 📡 政策雷达 · {company_name}\n> 今天没有匹配到新政策。"
    else:
        lines = [f"## 📡 政策雷达 · {company_name} · 今日 {len(matches_payload)} 条匹配\n"]
        for i, m in enumerate(matches_payload, 1):
            color = "🟢" if m["score"] >= 80 else ("🔵" if m["score"] >= 60 else "🟣")
            amount = f" 💰 {m['amount']}" if m.get("amount") else ""
            deadline = f" ⏰ {m['deadline']}" if m.get("deadline") else ""
            lines.append(
                f"> **{color} {m['score']}% | {m['type']}** <font color=\"comment\">{m['title']}</font>{amount}{deadline}"
            )
        content = "\n".join(lines)
    return {"msgtype": "markdown", "markdown": {"content": content}}


def format_payload(platform: str, company_name: str, matches_payload: list[dict]) -> dict:
    """按平台格式化 payload。"""
    if platform == PLATFORM_FEISHU:
        return _format_payload_feishu(company_name, matches_payload)
    if platform == PLATFORM_WECOM:
        return _format_payload_wecom(company_name, matches_payload)
    return _format_payload_generic(company_name, matches_payload)


async def _do_push(
    webhook_url: str,
    body_bytes: bytes,
    headers: dict,
    *,
    timeout: float,
) -> tuple[bool, int | None, str | None]:
    """单次 push，返回 (ok, status_code, error_msg)。"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                webhook_url,
                content=body_bytes,
                headers={"Content-Type": "application/json", **headers},
            )
            if r.status_code >= 500 or r.status_code == 429:
                # 5xx/429 视为可重试错误
                return False, r.status_code, f"server error {r.status_code}"
            r.raise_for_status()
            return True, r.status_code, None
    except httpx.TimeoutException:
        return False, None, "timeout"
    except httpx.HTTPStatusError as e:
        # 4xx 不可重试（客户端问题）
        return False, e.response.status_code, f"http {e.response.status_code}"
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"


# 重试配置：最多 3 次，指数退避 2/8/30 秒
RETRY_DELAYS = [2, 8, 30]


async def push_to_webhook(
    subscription: Subscription,
    matches: list[tuple[Match, Policy]],
    *,
    timeout: float = 10.0,
    max_retries: int = 3,
) -> dict:
    """把 matches 推送到 subscription.webhook_url。

    重试策略：失败时指数退避（2/8/30s），最多 3 次。
    4xx 错误（客户端问题）不重试；5xx/429/timeout 重试。
    最终失败返回 {"ok": False, "error": ..., "retries": N, "dead_letter": True}，
    调用方负责入死信表。

    返回 {"ok", "status_code", "platform", "signed", "retries", "error"}
    """
    if not subscription.webhook_url:
        return {"ok": False, "error": "no webhook_url configured"}

    platform = subscription.platform_hint or detect_platform(subscription.webhook_url)
    if platform not in VALID_PLATFORMS:
        platform = PLATFORM_GENERIC

    matches_payload = [_format_match_for_payload(m, pol) for m, pol in matches]
    company_name = subscription.company.name if subscription.company else "(unknown)"

    body = format_payload(platform, company_name, matches_payload)

    # HMAC 签名（如果设了 secret）
    headers = {}
    body_bytes = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if subscription.webhook_secret:
        sig = hmac.new(
            subscription.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        headers[SIGNATURE_HEADER] = f"sha256={sig}"

    # 重试循环
    last_error = None
    last_status = None
    for attempt in range(max_retries):
        ok, status, err = await _do_push(
            subscription.webhook_url, body_bytes, headers, timeout=timeout
        )
        if ok:
            logger.info(
                "push ok: sub=%d matches=%d platform=%s status=%d attempt=%d signed=%s",
                subscription.id, len(matches), platform, status, attempt + 1, bool(headers),
            )
            return {
                "ok": True,
                "status_code": status,
                "platform": platform,
                "signed": bool(headers),
                "retries": attempt,
            }
        last_error = err
        last_status = status

        # 4xx 不重试（客户端配置错误，重试也没用）
        if status is not None and 400 <= status < 500 and status != 429:
            logger.warning(
                "push failed (4xx, no retry): sub=%d status=%d err=%s",
                subscription.id, status, err,
            )
            break

        # 还有重试机会则 sleep
        if attempt < max_retries - 1:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            logger.warning(
                "push failed (will retry in %ds): sub=%d attempt=%d err=%s",
                delay, subscription.id, attempt + 1, err,
            )
            import asyncio
            await asyncio.sleep(delay)
        else:
            logger.error(
                "push failed (max retries): sub=%d attempts=%d err=%s",
                subscription.id, attempt + 1, err,
            )

    return {
        "ok": False,
        "error": last_error,
        "status_code": last_status,
        "platform": platform,
        "signed": bool(headers),
        "retries": max_retries,
        "dead_letter": True,  # 标志：调用方应入死信
    }
