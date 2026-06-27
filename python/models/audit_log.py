"""审计日志表：所有写操作 + 鉴权失败都留痕。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from python.models.base import Base, get_session


class AuditLog(Base):
    """一条审计记录。

    actor = 谁做的（admin 用户名 / 'anonymous'）
    action = 什么操作（login / create / update / delete / push / crawl / config）
    target_type = 资源类型（subscription / policy / source / company / llm_config / auth）
    target_id = 资源 ID
    detail = JSON 字符串（before/after/extra）
    ip / ua = 请求源
    status = success / failed
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), default="anonymous", nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    ua: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.id} {self.actor} {self.action} {self.target_type}:{self.target_id} {self.status}>"


async def write_audit(
    actor: str,
    action: str,
    target_type: str = "",
    target_id: str = "",
    detail: str = "",
    ip: str = "",
    ua: str = "",
    status: str = "success",
) -> None:
    """异步写审计日志（不阻塞主流程）。"""
    try:
        async with get_session() as session:
            session.add(AuditLog(
                actor=actor[:64],
                action=action[:32],
                target_type=target_type[:32],
                target_id=str(target_id)[:64],
                detail=detail[:5000],
                ip=ip[:64],
                ua=ua[:256],
                status=status,
            ))
            await session.commit()
    except Exception:
        # 审计日志失败不影响主流程
        import logging
        logging.getLogger(__name__).exception("failed to write audit log")
