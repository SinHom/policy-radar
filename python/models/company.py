"""企业档案表：C 端用户/AI 工具通过 MCP 注册的企业。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python.models.base import Base


class Company(Base):
    """一个被监控政策的企业（C 端订阅主体或 B 端运营管理的客户）。"""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scale: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # ["高新技术", "专精特新"]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    subscription: Mapped[Optional["Subscription"]] = relationship(  # type: ignore[name-defined]
        "Subscription", back_populates="company", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Company {self.id} {self.name}>"
