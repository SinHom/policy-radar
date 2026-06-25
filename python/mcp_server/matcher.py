"""规则匹配引擎：按 subscription.types/regions/keywords 给 policy 打分。

MVP 阶段不做 LLM 深度匹配，纯规则预筛：
- 类型匹配：policy.summary_type ∈ subscription.types  → +40
- 地区匹配：policy 地区 ⊆ subscription.regions       → +30
- 关键词匹配：policy 关键词 ∩ subscription.keywords  → +30
- 阈值：score >= 30 才入库 matches
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from python.models import Match, Policy, Subscription
from python.models.base import get_session

logger = logging.getLogger(__name__)

# 评分权重
SCORE_TYPE_MATCH = 40
SCORE_REGION_MATCH = 30
SCORE_KEYWORD_MATCH = 30
SCORE_THRESHOLD = 30

# 默认只看最近 N 天的政策
DEFAULT_DAYS_BACK = 30


def _policy_region_match(policy: Policy, regions: list[str]) -> bool:
    """判断 policy 地区是否命中 subscription.regions 中任一。

    MVP 简化：用 title + raw_content 前 200 字做粗略匹配。
    """
    if not regions:
        return True  # 没设地区限制就匹配
    text = (policy.title or "") + " " + (policy.raw_content or "")[:200]
    return any(r in text for r in regions if r)


def _score_policy(policy: Policy, sub: Subscription) -> tuple[int, list[str]]:
    """对 (policy, subscription) 打分，返回 (score, reasons)。"""
    score = 0
    reasons: list[str] = []

    sub_types = sub.types or []
    sub_regions = sub.regions or []
    sub_keywords = sub.keywords or []

    # 1. 类型匹配
    if policy.summary_type and sub_types:
        if policy.summary_type in sub_types:
            score += SCORE_TYPE_MATCH
            reasons.append(f"类型匹配:{policy.summary_type}")
    elif not sub_types:
        score += SCORE_TYPE_MATCH  # 没设类型 = 全匹配
        reasons.append("未设类型限制")

    # 2. 地区匹配
    if _policy_region_match(policy, sub_regions):
        score += SCORE_REGION_MATCH
        if sub_regions:
            reasons.append(f"地区匹配:{','.join(sub_regions)}")
        else:
            reasons.append("未设地区限制")

    # 3. 关键词匹配
    if sub_keywords:
        pol_kw = (policy.summary_data or {}).get("keywords") or []
        pol_text = (policy.title or "") + " " + (policy.summary_text or "")
        hit_kws = [kw for kw in sub_keywords if kw in pol_text or kw in pol_kw]
        if hit_kws:
            score += SCORE_KEYWORD_MATCH
            reasons.append(f"关键词命中:{','.join(hit_kws)}")

    return score, reasons


async def run_match_for_subscription(
    sub: Subscription,
    *,
    days_back: int = DEFAULT_DAYS_BACK,
) -> list[Match]:
    """对单个 subscription 跑一次匹配，写入 matches 表（去重）。"""
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    new_matches: list[Match] = []

    async with get_session() as session:
        # 候选 policies：最近 N 天有摘要的
        stmt = (
            select(Policy)
            .where(Policy.summary_text.isnot(None))
            .where(Policy.crawled_at >= cutoff)
            .order_by(Policy.id)
        )
        policies = list((await session.execute(stmt)).scalars().all())

        if not policies:
            logger.info("subscription %d: no recent policies", sub.id)
            return []

        # 已匹配过的 policy_id 集合（去重）
        existing_stmt = select(Match.policy_id).where(Match.subscription_id == sub.id)
        existing_pids = set(
            (await session.execute(existing_stmt)).scalars().all()
        )

        for pol in policies:
            if pol.id in existing_pids:
                continue
            score, reasons = _score_policy(pol, sub)
            if score < SCORE_THRESHOLD:
                continue
            m = Match(
                subscription_id=sub.id,
                policy_id=pol.id,
                score=score,
                reasons=reasons,
                pushed=False,
            )
            session.add(m)
            new_matches.append(m)
            logger.info(
                "subscription %d: matched policy %d score=%d (%s)",
                sub.id, pol.id, score, ", ".join(reasons),
            )

    logger.info(
        "subscription %d: %d new matches (out of %d candidates)",
        sub.id, len(new_matches), len(policies),
    )
    return new_matches


async def run_match_all(
    *,
    days_back: int = DEFAULT_DAYS_BACK,
) -> dict:
    """对所有 enabled subscriptions 跑一次匹配。

    返回 {"subscriptions": N, "total_matches": M}
    """
    async with get_session() as session:
        stmt = select(Subscription).where(Subscription.enabled.is_(True))
        subs = list((await session.execute(stmt)).scalars().all())

    total_new = 0
    for sub in subs:
        try:
            new = await run_match_for_subscription(sub, days_back=days_back)
            total_new += len(new)
        except Exception as e:
            logger.exception("subscription %d match failed: %s", sub.id, e)

    logger.info("match all: %d subs, %d new matches", len(subs), total_new)
    return {"subscriptions": len(subs), "total_matches": total_new}
