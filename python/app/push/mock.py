"""Mock 通道：把推送内容写到 mock_wechat 服务（开发测试用）。"""

from __future__ import annotations

import logging

import httpx

from python.app.config import get_settings
from python.app.push.dispatcher import PushContent, PushResult, register

logger = logging.getLogger(__name__)


@register("mock")
async def send(content: PushContent, config: dict) -> PushResult:
    """推送到 mock 微信服务。"""
    settings = get_settings()
    target = f"sub-{content.company_id or 'unknown'}"

    # 构造微信 iLink 风格消息
    lines = [
        "📡 政策雷达 · 推送",
        f"📅 {content.deadline or '即时'}",
        "━━━━━━━━━━━━━━━",
        f"🏷 {content.summary_type or '其他'}",
        content.title,
        content.summary[:200] if content.summary else "",
    ]
    if content.amount:
        lines.append(f"💰 {content.amount}")
    if content.deadline:
        lines.append(f"⏰ 截止 {content.deadline}")
    if content.company_name:
        lines.append(f"🎯 面向: {content.company_name}")
    msg = "\n".join([l for l in lines if l])

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.mock_wechat_url}/sendmessage",
                json={
                    "context_token": target,
                    "message": {"message_type": 1, "content": msg},
                },
            )
            r.raise_for_status()
    except Exception as e:
        return PushResult(ok=False, channel="mock", target=target, error=str(e)[:300])

    return PushResult(ok=True, channel="mock", target=target)
