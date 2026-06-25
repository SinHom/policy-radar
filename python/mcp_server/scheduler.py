"""APScheduler 定时任务：每日 07:00 跑匹配、08:30 推 webhook；每周五 08:30 周报。

调用方式：
    from python.mcp_server.scheduler import start_scheduler
    start_scheduler()  # 启动后台
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from python.mcp_server.matcher import run_match_all
from python.mcp_server.webhook import push_to_webhook, _do_push
from python.models import Match, Policy, PushDeadLetter, Subscription
from python.models.base import get_session
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def daily_match_job() -> None:
    """每日 07:00：跑全量匹配。"""
    logger.info("=== daily_match_job start at %s ===", datetime.now().isoformat())
    try:
        result = await run_match_all()
        logger.info("daily_match_job done: %s", result)
    except Exception as e:
        logger.exception("daily_match_job failed: %s", e)


async def daily_push_job() -> None:
    """每日 08:30：推未推送的 matches 到 webhook。"""
    logger.info("=== daily_push_job start at %s ===", datetime.now().isoformat())
    try:
        pushed = await push_pending_matches()
        logger.info("daily_push_job done: pushed=%d", pushed)
    except Exception as e:
        logger.exception("daily_push_job failed: %s", e)


async def weekly_push_job() -> None:
    """每周五 08:30：周报推送（复用 daily_push 逻辑）。"""
    logger.info("=== weekly_push_job start at %s ===", datetime.now().isoformat())
    try:
        pushed = await push_pending_matches(weekly=True)
        logger.info("weekly_push_job done: pushed=%d", pushed)
    except Exception as e:
        logger.exception("weekly_push_job failed: %s", e)


async def push_pending_matches(*, weekly: bool = False) -> int:
    """把 enabled 且 push_schedule 匹配的 subscriptions 的未推送 matches 发出去。

    逻辑：
    1. 查 enabled 且 webhook_url 非空的 subscriptions
    2. 过滤出 push_schedule 匹配的：daily (无论周几) / weekly (周五)
    3. 取每个 sub 的未推送 matches + 对应 policy
    4. 调 push_to_webhook
    5. 成功的标记 pushed=True + pushed_at
    6. 失败的入死信表
    """
    is_friday = datetime.now().weekday() == 4  # 周五

    async with get_session() as session:
        # 候选 subscriptions
        stmt = select(Subscription).where(Subscription.enabled.is_(True))
        subs = list((await session.execute(stmt)).scalars().all())

    # 过滤 schedule
    targets = []
    for s in subs:
        if not s.webhook_url:
            continue
        if s.push_schedule == "daily":
            if not weekly:  # daily_push_job
                targets.append(s)
        elif s.push_schedule == "weekly":
            if weekly and is_friday:
                targets.append(s)
        # realtime/manual 跳过（实时触发或仅 pull）

    pushed_total = 0
    for sub_id in [s.id for s in targets]:
        # 每次 push 独立 session，避免跨 session 用 detached 对象
        async with get_session() as session:
            # 重新 query sub（带 company 关系）
            from sqlalchemy.orm import selectinload
            stmt_sub = select(Subscription).where(Subscription.id == sub_id).options(
                selectinload(Subscription.company)
            )
            sub = (await session.execute(stmt_sub)).scalar_one_or_none()
            if sub is None:
                continue

            # 查未推送的 matches
            stmt = (
                select(Match, Policy)
                .join(Policy, Match.policy_id == Policy.id)
                .where(Match.subscription_id == sub.id)
                .where(Match.pushed.is_(False))
                .order_by(Match.score.desc())
                .limit(20)
            )
            rows = list((await session.execute(stmt)).all())
            if not rows:
                continue

            result = await push_to_webhook(sub, rows)
            if result.get("ok"):
                # 标记 pushed
                for m, _ in rows:
                    m.pushed = True
                    m.pushed_at = datetime.utcnow()
                sub.last_push_at = datetime.utcnow()
                pushed_total += len(rows)
                logger.info("pushed %d matches for sub=%d", len(rows), sub.id)
            elif result.get("dead_letter"):
                # 入死信
                from python.mcp_server.tools.push import _build_payload_snapshot
                body_bytes = _build_payload_snapshot(sub, rows)
                headers = {}
                import hmac, hashlib
                from python.mcp_server.webhook import SIGNATURE_HEADER
                # 重新计算签名（因为 webhook_secret 可能改过）
                from python.mcp_server.webhook import json as _json, hmac as _hmac, hashlib as _hashlib
                body_for_sig = _json.dumps(body_bytes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if sub.webhook_secret:
                    sig = _hmac.new(sub.webhook_secret.encode("utf-8"), body_for_sig, _hashlib.sha256).hexdigest()
                    headers[SIGNATURE_HEADER] = f"sha256={sig}"

                dead = PushDeadLetter(
                    subscription_id=sub.id,
                    webhook_url=sub.webhook_url or "",
                    payload=body_bytes,
                    headers=headers,
                    error_msg=result.get("error", "unknown"),
                    last_status_code=result.get("status_code"),
                    attempts=result.get("retries", 0) + 1,
                    retry_count=0,
                    next_retry_at=datetime.utcnow(),
                    resolved=False,
                )
                session.add(dead)
                logger.error(
                    "push failed -> dead letter: sub=%d err=%s",
                    sub.id, result.get("error"),
                )
            else:
                logger.warning("push failed for sub=%d: %s", sub.id, result.get("error"))

    return pushed_total


async def dead_letter_retry_job() -> int:
    """每日 09:00 重发未 resolve 的死信。

    最多重试 3 次（retry_count 字段），超过则标记 resolved=False 但放弃（保留审计）。
    """
    import asyncio
    from python.mcp_server.webhook import _do_push

    retried = 0
    resolved = 0
    async with get_session() as session:
        # 找未 resolve 且 next_retry_at <= now 且 retry_count < 3
        stmt = (
            select(PushDeadLetter)
            .where(PushDeadLetter.resolved.is_(False))
            .where(PushDeadLetter.retry_count < 3)
        )
        deads = list((await session.execute(stmt)).scalars().all())
        for d in deads:
            body_bytes = json.dumps(d.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ok, status, err = await _do_push(d.webhook_url, body_bytes, d.headers, timeout=10.0)
            d.retry_count += 1
            d.last_status_code = status
            d.error_msg = err or d.error_msg
            if ok:
                d.resolved = True
                d.resolved_at = datetime.utcnow()
                resolved += 1
                logger.info("dead letter %d resolved on retry %d", d.id, d.retry_count)
            else:
                d.next_retry_at = datetime.utcnow() + timedelta(hours=24)
                logger.warning(
                    "dead letter %d retry %d failed: %s",
                    d.id, d.retry_count, err,
                )
            retried += 1
            await asyncio.sleep(0.5)  # 避免雪崩

    logger.info("dead_letter_retry_job: retried=%d resolved=%d", retried, resolved)
    return resolved


def build_scheduler() -> AsyncIOScheduler:
    """构造 scheduler（不启动）。"""
    sched = AsyncIOScheduler(timezone="Asia/Shanghai")
    # 每日 07:00 跑匹配
    sched.add_job(daily_match_job, CronTrigger(hour=7, minute=0), id="daily_match")
    # 每日 08:30 推 daily push
    sched.add_job(daily_push_job, CronTrigger(hour=8, minute=30), id="daily_push")
    # 每周五 08:30 推 weekly push
    sched.add_job(weekly_push_job, CronTrigger(day_of_week="fri", hour=8, minute=30), id="weekly_push")
    # 每日 09:00 重发死信（重试 3 次后仍未 resolve 则放弃）
    sched.add_job(dead_letter_retry_job, CronTrigger(hour=9, minute=0), id="dead_letter_retry")
    return sched


def start_scheduler() -> AsyncIOScheduler:
    """启动 scheduler（后台非阻塞）。"""
    sched = build_scheduler()
    sched.start()
    logger.info("Scheduler started: daily_match@07:00 / daily_push@08:30 / weekly_push@fri 08:30")
    return sched
