"""Scheduler 调度的周报推送(每周一次)。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from python.app.push.daily_report import build_weekly_report
from python.app.push.facade import push_daily_cards
from python.models import Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)


# 每周一/三/五 09:00 UTC(= 北京 17:00 — 改用 UTC 1:00 = 北京 9:00 固定)
WEEKLY_DAY_HOURS_UTC = {0: 1, 2: 1, 4: 1}  # 周一/三/五 UTC 1:00
LAST_TRIGGERED_KEY = "weekly"


async def run_weekly_all_subs() -> int:
    """对所有 enabled + push_channel in (feishu, webhook) 订阅推周报。

    Returns: 成功推送数。
    """
    sent_count = 0
    targets: list[tuple[int, str, dict, str | None]] = []
    async with get_session() as session:
        stmt = (
            select(Subscription)
            .where(Subscription.enabled.is_(True))
            .where(Subscription.push_channel.in_(["feishu", "webhook"]))
        )
        subs = (await session.execute(stmt)).scalars().all()
        for s in subs:
            config = s.push_config or {}
            if not config.get("webhook_url"):
                continue
            comp = s.company
            company_name = comp.name if comp else None
            targets.append((s.id, s.push_channel, dict(config), company_name))

    cards = await build_weekly_report("weekly")
    if not cards:
        return 0

    for sub_id, channel, config, company_name in targets:
        try:
            result = await push_daily_cards(cards, channel, config, company_name=company_name)
            if result.get("ok"):
                sent_count += 1
                logger.info("Weekly: sub=%s sent=%d/%d", sub_id, result.get("sent"), result.get("total"))
            else:
                logger.warning("Weekly: sub=%s failed %s", sub_id, result.get("errors") or result.get("error"))
        except Exception as e:
            logger.exception("Weekly: sub=%s 异常 %s", sub_id, e)
    return sent_count
