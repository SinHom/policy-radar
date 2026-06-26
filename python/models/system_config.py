"""系统配置表：key-value 存动态配置（LLM 接入信息等）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from python.models.base import Base, get_session
from sqlalchemy import select


class SystemConfig(Base):
    """系统配置：key-value 形式，value 是 JSON。"""

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<SystemConfig {self.key}>"

    @staticmethod
    async def get(session, key: str, default: Any = None) -> Any:
        """读配置。"""
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )).scalar_one_or_none()
        return cfg.value if cfg else default

    @staticmethod
    async def set(session, key: str, value: Any) -> None:
        """写配置。"""
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )).scalar_one_or_none()
        if cfg:
            cfg.value = value
            cfg.updated_at = datetime.utcnow()
        else:
            cfg = SystemConfig(key=key, value=value)
            session.add(cfg)
        await session.flush()
