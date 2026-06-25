"""推送记录表：每次推送到微信（mock 或真实）都留痕。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python.models.base import Base


class PushLog(Base):
    """一次推送动作 = 一条记录。

    target 是推送目标（微信用户/群/Mock）；content 是实际推送内容；
    status 是 success / failed。
    """

    __tablename__ = "push_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    policy: Mapped["Policy"] = relationship("Policy", back_populates="push_logs")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<PushLog {self.id} policy={self.policy_id} status={self.status}>"
