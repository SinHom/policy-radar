"""iLink 收消息路由：长轮询 + 命令分发。

支持命令：
- "1" / "2" / "3" ...       → 查第 N 条匹配的详情
- "详情 <policy_id>"        → 查指定 ID
- "咨询" / "联系顾问"       → 发顾问名片/二维码
- "暂停" / "恢复"           → 切换订阅
- 其他                       → LLM 自由对话（政策相关）

运行：
    python -m wechat.message_router
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from typing import Any, Optional

import httpx
from sqlalchemy import desc, select

from python.app.config import get_settings
from python.models import Company, Match, Policy, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)


async def fetch_new_messages(cursor: str = "", long_poll_timeout: int = 30) -> dict:
    """从 iLink 拉新消息。

    返回 iLink API 响应：{"messages": [...], "cursor": "next-..."}
    """
    from python.wechat.ilink_client import get_client
    client = get_client()
    try:
        return await client.get_updates(cursor=cursor, long_poll_timeout=long_poll_timeout)
    except Exception as e:
        logger.error("iLink get_updates failed: %s", e)
        return {"messages": [], "cursor": cursor}


async def send_reply(context_token: str, content: str, message_type: int = 1) -> bool:
    """发回复到 iLink。"""
    from python.wechat.ilink_client import get_client
    client = get_client()
    try:
        r = await client.send_message(context_token, content, message_type=message_type)
        return r.get("status") == "ok"
    except Exception as e:
        logger.error("iLink send_message failed: %s", e)
        return False


# === 命令解析 ===

# 匹配命令："1" / "2" / "详情 12" / "咨询" / "暂停" / "恢复"
CMD_DETAIL_NUM = re.compile(r"^\s*(\d+)\s*$")
CMD_DETAIL_ID = re.compile(r"^\s*(?:详情|查看|查)\s*(\d+)\s*$")
CMD_CONSULT = re.compile(r"^\s*(?:咨询|联系|顾问|人工)\s*$")
CMD_PAUSE = re.compile(r"^\s*(?:暂停|停止|不要)\s*$")
CMD_RESUME = re.compile(r"^\s*(?:恢复|继续|开始)\s*$")
CMD_HELP = re.compile(r"^\s*(?:帮助|help|菜单|\?)\s*$", re.IGNORECASE)


def parse_command(text: str) -> str:
    """返回命令类型：detail_num / detail_id / consult / pause / resume / help / chat"""
    if CMD_DETAIL_NUM.match(text):
        return "detail_num"
    if CMD_DETAIL_ID.match(text):
        return "detail_id"
    if CMD_CONSULT.match(text):
        return "consult"
    if CMD_PAUSE.match(text):
        return "pause"
    if CMD_RESUME.match(text):
        return "resume"
    if CMD_HELP.match(text):
        return "help"
    return "chat"


# === 业务处理 ===

async def _get_user_subscription(context_token: str) -> Optional[Subscription]:
    """根据 iLink context_token 找订阅。

    MVP 简化：context_token 直接当 user_id（或 user_id 的 hash），用最近一个订阅
    实际 iLink 上线后需要 user_id → subscription 映射表
    """
    async with get_session() as session:
        # 取最近一个 enabled 订阅（MVP 简化：单租户场景）
        stmt = select(Subscription).where(Subscription.enabled.is_(True)).limit(1)
        sub = (await session.execute(stmt)).scalar_one_or_none()
        return sub


async def _format_match(m: Match, pol: Policy) -> str:
    return (
        f"📌 {pol.title}\n"
        f"类型：{pol.summary_type or '其他'}\n"
        f"摘要：{pol.summary_text or '(无)'}\n"
        f"金额：{(pol.summary_data or {}).get('amount') or '无'}\n"
        f"截止：{(pol.summary_data or {}).get('deadline') or '无'}\n"
        f"链接：{pol.url}\n"
    )


async def handle_command(text: str, context_token: str) -> str:
    """处理用户命令，返回回复文本。"""
    cmd = parse_command(text)
    sub = await _get_user_subscription(context_token)

    if sub is None:
        return "你还没有订阅政策，请先通过 start_setup 注册。"

    if cmd == "help":
        return (
            "📡 政策雷达 · 命令菜单\n"
            "━━━━━━━━━━━━━━━\n"
            "1/2/3...     查第 N 条匹配\n"
            "详情 <id>    查指定政策\n"
            "咨询         联系顾问\n"
            "暂停         暂停推送\n"
            "恢复         恢复推送\n"
            "或直接告诉我你想了解的政策"
        )

    if cmd == "pause":
        sub.enabled = False
        return "✅ 已暂停推送。需要时回复「恢复」。"

    if cmd == "resume":
        sub.enabled = True
        return "✅ 已恢复推送。"

    if cmd in ("detail_num", "detail_id"):
        if cmd == "detail_num":
            n = int(CMD_DETAIL_NUM.match(text).group(1))
            # 查第 N 条（按 score 倒序）
            async with get_session() as session:
                stmt = (
                    select(Match, Policy)
                    .join(Policy, Match.policy_id == Policy.id)
                    .where(Match.subscription_id == sub.id)
                    .order_by(desc(Match.score), desc(Match.id))
                    .offset(n - 1).limit(1)
                )
                row = (await session.execute(stmt)).first()
            if not row:
                return f"没有第 {n} 条匹配。"
            m, pol = row
            return await _format_match(m, pol)
        else:
            pid = int(CMD_DETAIL_ID.match(text).group(1))
            async with get_session() as session:
                stmt = select(Policy).where(Policy.id == pid)
                pol = (await session.execute(stmt)).scalar_one_or_none()
            if not pol:
                return f"找不到政策 #{pid}。"
            return (
                f"📌 #{pid} {pol.title}\n"
                f"类型：{pol.summary_type or '其他'}\n"
                f"摘要：{pol.summary_text or '(无)'}\n"
                f"链接：{pol.url}"
            )

    if cmd == "consult":
        # TODO: 实际发送顾问二维码图片
        return (
            "🎯 政策申报顾问\n"
            "━━━━━━━━━━━━━━━\n"
            "Fangyi · 100+ 企业申报经验\n"
            "[二维码图片]\n"
            "扫码添加，免费评估申报资格"
        )

    if cmd == "chat":
        # LLM 自由对话
        from python.ai.llm_client import get_llm_client
        from python.app.config import get_settings
        try:
            settings = get_settings()
            client = get_llm_client()
            resp = await client.chat(
                system="你是政策雷达助手。简洁回答用户关于政策的问题。",
                user=text[:500],
                temperature=0.5,
                max_tokens=500,
            )
            return resp
        except Exception as e:
            logger.warning("LLM chat failed: %s", e)
            return "抱歉，AI 服务暂不可用，请稍后重试。"

    return "未知命令。回复「帮助」查看菜单。"


# === 主循环 ===

async def long_poll_loop(cursor: str = "", poll_interval: int = 5):
    """主循环：长轮询 iLink，处理消息，回复。"""
    logger.info("iLink message router started, cursor=%s", cursor)
    while True:
        try:
            resp = await fetch_new_messages(cursor=cursor, long_poll_timeout=30)
            msgs = resp.get("messages", [])
            new_cursor = resp.get("cursor", cursor)
            if msgs:
                logger.info("received %d new messages", len(msgs))
                for m in msgs:
                    ctx = m.get("context_token", "")
                    content = m.get("content", "").strip()
                    if not ctx or not content:
                        continue
                    try:
                        reply = await handle_command(content, ctx)
                        if reply:
                            await send_reply(ctx, reply)
                    except Exception as e:
                        logger.exception("handle %r failed: %s", content, e)
                cursor = new_cursor
            else:
                # 无新消息时短暂 sleep（避免 CPU 100%）
                await asyncio.sleep(poll_interval)
        except Exception as e:
            logger.exception("long_poll_loop error: %s", e)
            await asyncio.sleep(10)


def main() -> int:
    from python.app.logging_config import setup_logging
    setup_logging()
    try:
        asyncio.run(long_poll_loop())
    except KeyboardInterrupt:
        logger.info("interrupted, exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
