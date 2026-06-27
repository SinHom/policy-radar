"""推送内容数据结构 + 分发器。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PushContent:
    """要推送的内容。"""
    policy_id: int
    title: str
    summary: str
    summary_type: Optional[str] = None
    amount: Optional[str] = None
    deadline: Optional[str] = None
    url: Optional[str] = None
    # 来源元信息
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    # 目标元信息（接收方公司）
    company_id: Optional[int] = None
    company_name: Optional[str] = None


@dataclass
class PushResult:
    """推送结果。"""
    ok: bool
    channel: str
    target: str  # 接收方标识（用于 push_log.target）
    error: Optional[str] = None
    raw_response: Optional[dict] = None


@dataclass
class TextPayload:
    """飞书/通用文本推送的统一载荷。"""
    title: str
    lines: list[str] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)
    # 按钮格式：[{"text": "查看详情", "url": "..."}]


async def dispatch(content: PushContent, channel: str, config: dict) -> PushResult:
    """根据 channel 选择通道发送。"""
    from python.app.push import feishu, mock, webhook
    # SSRF 防护：webhook 类通道必校验 URL
    if channel in ("feishu", "webhook"):
        webhook_url = (config or {}).get("webhook_url")
        if webhook_url:
            from python.app.security import validate_webhook_url
            import os as _os
            allow_private = _os.environ.get("ALLOW_PRIVATE_WEBHOOK") == "1"
            ok, err = validate_webhook_url(webhook_url, allow_private=allow_private)
            if not ok:
                return PushResult(
                    ok=False, channel=channel, target="-",
                    error=f"webhook URL invalid: {err}",
                )
    fn = CHANNELS.get(channel)
    if not fn:
        return PushResult(ok=False, channel=channel, target="-", error=f"unknown channel: {channel}")
    try:
        return await fn(content, config)
    except Exception as e:
        logger.exception("push dispatch failed: channel=%s", channel)
        return PushResult(ok=False, channel=channel, target="-", error=str(e)[:300])


# 通道注册表
CHANNELS: dict = {}


def register(name: str):
    """装饰器：注册通道。"""
    def deco(fn):
        CHANNELS[name] = fn
        return fn
    return deco


# 导入并自动注册（用装饰器）
from python.app.push import mock as _mock  # noqa: E402
from python.app.push import feishu as _feishu  # noqa: E402
from python.app.push import webhook as _webhook  # noqa: E402
