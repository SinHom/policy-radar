"""政策源表：配置每个爬虫源（URL、选择器、频率等）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python.models.base import Base


class PolicySource(Base):
    """一个爬虫源 = 一条 JSON 配置 + 一个源 ID。

    source_id 是稳定标识（如 'sz_gxj'），id 是数据库自增主键。
    spider_config 存选择器、render_js、frequency 等参数。
    """

    __tablename__ = "policy_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 国家级/省级/市级
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 北京/广东/深圳
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 发改委/工信局/科技局
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 多个标签，如 ["国家级","发改","AI"]
    spider_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    frequency: Mapped[str] = mapped_column(String(16), default="daily", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_crawl_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending/ok/failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # 反向引用：此源爬到的所有政策
    policies: Mapped[list["Policy"]] = relationship(  # type: ignore[name-defined]
        "Policy", back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PolicySource {self.source_id} {self.name}>"
