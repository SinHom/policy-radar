"""Scheduler 调度的日报推送:遍历所有 enabled+feishu/webhook 订阅,生成日报卡片并推送。"""
from __future__ import annotations

import logging

from sqlalchemy import select

from python.app.push.daily_report import build_daily_report
from python.app.push.dispatcher import PushResult
from python.app.push.facade import push_daily_cards
from python.models import Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)


async def run_daily_report_all_subs(slot: str = "早间") -> int:
    """对所有 enabled + push_channel in (feishu, webhook) 订阅推日报。

    Returns: 成功推送数。
    """
    sent_count = 0
    async with get_session() as session:
        stmt = (
            select(Subscription)
            .where(Subscription.enabled.is_(True))
            .where(Subscription.push_channel.in_(["feishu", "webhook"]))
        )
        subs = (await session.execute(stmt)).scalars().all()
        # 准备 (sub_id, channel, config) 列表
        targets = []
        for s in subs:
            config = s.push_config or {}
            if not config.get("webhook_url"):
                logger.info("Daily report: 跳过 sub=%s (无 webhook_url)", s.id)
                continue
            targets.append((s.id, s.push_channel, config, s.company.name if s.company else None))

    # 卡片只生成 1 次(同样的 slot 推给所有订阅)
    cards = await build_daily_report(slot)
    if not cards:
        logger.info("Daily report %s: 无卡片生成,跳过", slot)
        return 0

    for sub_id, channel, config, company_name in targets:
        try:
            result = await push_daily_cards(cards, channel, config, company_name=company_name)
            if result.get("ok"):
                sent_count += 1
                logger.info("Daily report %s: sub=%s 推送成功 sent=%d/%d", slot, sub_id,
                            result.get("sent"), result.get("total"))
            else:
                logger.warning("Daily report %s: sub=%s 推送失败 %s", slot, sub_id,
                               result.get("errors") or result.get("error"))
        except Exception as e:
            logger.exception("Daily report %s: sub=%s 异常 %s", slot, sub_id, e)
    return sent_count
