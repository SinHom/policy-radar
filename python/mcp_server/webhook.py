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


async def push_to_webhook(
    subscription: Subscription,
    matches: list[tuple[Match, Policy]],
    *,
    timeout: float = 10.0,
) -> dict:
    """把 matches 推送到 subscription.webhook_url。

    返回 {"ok": bool, "status_code": int, "platform": str, "error": Optional[str]}
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

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                subscription.webhook_url,
                content=body_bytes,  # 用 content 防止 httpx 重新序列化
                headers={"Content-Type": "application/json", **headers},
            )
            r.raise_for_status()
            logger.info(
                "push ok: sub=%d matches=%d platform=%s status=%d signed=%s",
                subscription.id, len(matches), platform, r.status_code, bool(headers),
            )
            return {"ok": True, "status_code": r.status_code, "platform": platform, "signed": bool(headers)}
    except Exception as e:
        logger.exception("push failed: sub=%d platform=%s err=%s", subscription.id, platform, e)
        return {"ok": False, "error": str(e), "platform": platform}
