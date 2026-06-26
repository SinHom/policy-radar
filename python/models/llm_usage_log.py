"""LLM 调用日志表：每次调大模型都留痕（用于 token 消耗统计 + 成本分析）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from python.models.base import Base


class LLMUsageLog(Base):
    """一条 LLM 调用 = 一条记录。

    记录：模型名、prompt/response token 数、cost（美元，可选）、
    关联 policy_id（如果用于摘要）、状态、错误信息。
    """

    __tablename__ = "llm_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Integer, default=0.0, nullable=False)  # 暂存 0，等接入定价
    purpose: Mapped[str] = mapped_column(String(32), default="summarize", nullable=False)
    # summarize / health_check / classify
    policy_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    # 0 = 不关联特定 policy
    status: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    error_msg: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<LLMUsage {self.id} model={self.model} in={self.input_tokens} out={self.output_tokens}>"
