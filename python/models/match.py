"""匹配结果表：每次匹配周期算一批，subscription × policy。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python.models.base import Base


class Match(Base):
    """一条匹配记录 = 1 个 subscription 命中 1 条 policy。"""

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("subscription_id", "policy_id", name="uq_match_sub_pol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-100
    reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # ["地区匹配:深圳", ...]
    pushed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pushed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="matches")  # type: ignore[name-defined]
    policy: Mapped["Policy"] = relationship("Policy")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Match {self.id} sub={self.subscription_id} pol={self.policy_id} score={self.score}>"
