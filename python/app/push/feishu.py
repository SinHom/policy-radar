"""飞书通道：自定义群机器人 webhook。

接入方式（用户侧）：
1. 飞书群里添加「群机器人」→ 「自定义机器人」
2. 选「安全设置」：可选「签名校验」（推荐）或「自定义关键词」
3. 复制 webhook URL，配置到订阅的 push_config.webhook_url
4. 签名密钥配 push_config.secret

推送格式：interactive card（交互式卡片），含标题/摘要/金额/截止/按钮
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Optional

import httpx

from python.app.push.dispatcher import PushContent, PushResult, register

logger = logging.getLogger(__name__)

FEISHU_BASE = "https://open.feishu.cn"


def _sign(secret: str, timestamp: int) -> str:
    """飞书签名校验：HMAC-SHA256(timestamp + "\\n" + secret)，base64 编码。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _build_card(content: PushContent, with_url: bool = True) -> dict:
    """构造飞书交互式卡片。"""
    fields = []
    if content.summary_type:
        fields.append(f"**类型:** {content.summary_type}")
    if content.amount:
        fields.append(f"**金额:** {content.amount}")
    if content.deadline:
        fields.append(f"**截止:** {content.deadline}")
    if content.source_name:
        fields.append(f"**来源:** {content.source_name}")
    if content.company_name:
        fields.append(f"**接收:** {content.company_name}")

    elements = [
        # 摘要正文
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": content.summary[:1500] if content.summary else "（无摘要）",
            },
        },
    ]
    if fields:
        elements.append({
            "tag": "div",
            "fields": fields,
        })
    # 分隔线
    elements.append({"tag": "hr"})
    # 按钮
    actions = []
    if content.url and content.url.startswith("http"):
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看详情"},
            "type": "primary",
            "url": content.url,
        })
    actions.append({
        "tag": "button",
        "text": {"tag": "plain_text", "content": "🌐 政策雷达"},
        "type": "default",
        "url": "http://43.155.161.54:8000/admin",  # 可配置
    })
    if actions:
        elements.append({"tag": "action", "actions": actions})
    # 脚注
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"📡 政策雷达 · policy #{content.policy_id}"},
        ],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": (content.title or "新政策")[:60],
            },
            "template": "blue",  # blue/red/orange/...
        },
        "elements": elements,
    }


@register("feishu")
async def send(content: PushContent, config: dict) -> PushResult:
    """推送到飞书群机器人 webhook。"""
    webhook_url: Optional[str] = config.get("webhook_url")
    secret: Optional[str] = config.get("secret")

    if not webhook_url:
        return PushResult(ok=False, channel="feishu", target="-",
                          error="feishu 通道未配置 webhook_url（请在订阅编辑里填）")

    card = _build_card(content)
    body: dict = {"msg_type": "interactive", "card": card}

    # 签名校验（如果配置了 secret）
    if secret:
        ts = int(time.time())
        body["timestamp"] = str(ts)
        body["sign"] = _sign(secret, ts)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(webhook_url, json=body)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return PushResult(ok=False, channel="feishu", target=webhook_url[:60],
                          error=str(e)[:300])

    # 飞书返回 {"code": 0, "msg": "success"} 或 {"StatusCode": 0, ...}
    code = data.get("code") or data.get("StatusCode") or 0
    if code != 0:
        return PushResult(ok=False, channel="feishu", target=webhook_url[:60],
                          error=data.get("msg") or data.get("Message") or f"feishu code={code}",
                          raw_response=data)

    return PushResult(ok=True, channel="feishu", target=webhook_url[:80], raw_response=data)
