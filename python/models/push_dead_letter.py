"""推送死信表：push 重试 3 次仍失败的，记入死信，scheduler 周期重发。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python.models.base import Base


class PushDeadLetter(Base):
    """一条死信 = 一次失败的推送。"""

    __tablename__ = "push_dead_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    # 失败时使用的 URL（如果后来 subscription 删了，还有 URL 备用）
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 完整的 JSON body（formatted payload）
    headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # 含 HMAC 签名 header
    error_msg: Mapped[str] = mapped_column(Text, nullable=False)
    last_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # 重发控制
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<PushDeadLetter {self.id} sub={self.subscription_id} attempts={self.attempts} resolved={self.resolved}>"
