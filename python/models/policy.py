"""政策表：原始政策 + 摘要字段合一（MVP 简化版）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python.models.base import Base


class Policy(Base):
    """一条政策记录。

    字段划分：
    - 原始信息：url(UNIQUE), title, raw_content, published_at, crawled_at
    - 摘要信息：summary_type, summary_text, summary_data(JSON), summary_model, summarized_at
    """

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("policy_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # 摘要（MVP 简化：summary_text 给人看，summary_data 存完整 JSON 给程序用）
    summary_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 补贴/贷款/税收/...
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    summary_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    summarized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # === 短字段(从 summary_data 提出来方便筛选/显示) ===
    amount: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # "100万"
    deadline: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # "2026-12-31"

    # === AI 业务解读(200字内,直接给企业看的"这政策对你怎么用") ===
    advisory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # === 按需抓全文 ===
    # NULL = 未抓(只存了 RSS 摘要);非空 = 已 playwright 抓过正文,缓存 data/mds/{id}.md
    full_text_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # 反向引用
    source: Mapped["PolicySource"] = relationship("PolicySource", back_populates="policies")  # type: ignore[name-defined]
    push_logs: Mapped[list["PushLog"]] = relationship(  # type: ignore[name-defined]
        "PushLog", back_populates="policy", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Policy {self.id} {self.title[:30]}>"
