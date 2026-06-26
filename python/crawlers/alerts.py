"""爬虫失败告警：连续失败 N 次时发通知。

告警通道（按顺序尝试）：
1. Webhook URL（环境变量 CRAWL_ALERT_WEBHOOK，飞书/企微/Slack）
2. 邮件（环境变量 CRAWL_ALERT_EMAIL）
3. 日志 ERROR（兜底）

设计原则：
- 失败：单次错误只 log，不发告警（避免噪声）
- 告警：连续 3 次失败才发（避免瞬时网络抖动误报）
- 恢复：连续 2 次成功发"已恢复"
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# source_id → 连续失败次数
_failure_count: dict[str, int] = defaultdict(int)
_success_count: dict[str, int] = defaultdict(int)
_threshold = 3


def record_success(source_id: str) -> None:
    """记录一次成功，触发"已恢复"告警（如果之前在告警中）。"""
    _failure_count[source_id] = 0
    _success_count[source_id] += 1
    if _success_count[source_id] == 2:
        _send_alert(
            source_id,
            level="info",
            message=f"✅ 爬虫已恢复（连续 2 次成功）",
        )


def record_failure(source_id: str, error: str) -> None:
    """记录一次失败，连续 3 次发告警。"""
    _failure_count[source_id] += 1
    _success_count[source_id] = 0
    if _failure_count[source_id] == _threshold:
        _send_alert(
            source_id,
            level="error",
            message=f"❌ 爬虫连续失败 {_threshold} 次\n最后错误：{error[:200]}",
        )
    elif _failure_count[source_id] > _threshold:
        # 后续失败只 log，不重复发告警（避免噪声）
        logger.error("[%s] continue failure (%d): %s", source_id, _failure_count[source_id], error)


def _send_alert(source_id: str, level: str, message: str) -> None:
    """发告警到 webhook / email / log。"""
    text = f"🤖 Policy Radar · {level.upper()}\n时间：{datetime.now().isoformat(timespec='seconds')}\n源：{source_id}\n{message}"

    # 1. Webhook
    webhook_url = os.environ.get("CRAWL_ALERT_WEBHOOK")
    if webhook_url:
        try:
            import asyncio
            asyncio.run(_post_webhook(webhook_url, text))
        except Exception as e:
            logger.error("webhook alert failed: %s", e)

    # 2. 邮件（占位，需要配置 SMTP）
    # TODO: 邮件告警

    # 3. Log
    if level == "error":
        logger.error(text)
    else:
        logger.info(text)


async def _post_webhook(url: str, text: str) -> None:
    """POST 到 webhook（兼容飞书/企微通用 JSON）。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 飞书格式
        if "feishu" in url or "lark" in url:
            payload = {"msg_type": "text", "content": {"text": text}}
        # 企微格式
        elif "weixin" in url:
            payload = {"msgtype": "markdown", "markdown": {"content": text}}
        # 通用
        else:
            payload = {"text": text}
        r = await client.post(url, json=payload)
        r.raise_for_status()
