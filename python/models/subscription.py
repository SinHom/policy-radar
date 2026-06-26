"""订阅规则表：1 个 company 对应 1 个 subscription（关注哪些政策 + 推送设置）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python.models.base import Base


class Subscription(Base):
    """订阅规则：types/regions/keywords 用于匹配；webhook_url/platform_hint 用于推送。"""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # ["补贴", "贷款"]
    regions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # ["深圳", "广东"]
    keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # ["专精特新"]
    push_schedule: Mapped[str] = mapped_column(String(16), default="daily", nullable=False)
    # realtime / daily / weekly / manual
    push_time: Mapped[str] = mapped_column(String(8), default="08:30", nullable=False)
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # 用于 HMAC 签名 (X-Policy-Radar-Signature: sha256=<hex>)
    # 接收方用同样密钥验证 body 未被篡改
    platform_hint: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # feishu / wecom / generic

    # === 推送渠道（多通道抽象） ===
    push_channel: Mapped[str] = mapped_column(String(16), default="mock", nullable=False)
    # mock / wechat / feishu / wecom / email / webhook
    push_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    # 渠道特定配置：
    # feishu:  {"webhook_url":"...","secret":"..."}（secret 可选，开启签名校验时必填）
    # wecom:   {"webhook_url":"..."}
    # webhook: {"webhook_url":"...","secret":"..."}（自定义 webhook，HMAC 签名）
    # email:   {"to":"a@x.com,b@y.com","smtp_host":"..."}
    # wechat:  {"bot_token":"...","chat_id":"..."}（未来 iLink）

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_push_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="subscription")  # type: ignore[name-defined]
    matches: Mapped[list["Match"]] = relationship(  # type: ignore[name-defined]
        "Match", back_populates="subscription", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Subscription {self.id} company={self.company_id} schedule={self.push_schedule}>"
