"""add LLM usage log + system config + policy source tags

Revision ID: 8a1b2c3d4e5f
Revises: 5b6702eb4d5b
Create Date: 2026-06-27 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "8a1b2c3d4e5f"
down_revision = "5b6702eb4d5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === LLM 使用日志 ===
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("model", sa.String(64), nullable=False, index=True),
        sa.Column("input_tokens", sa.Integer, default=0, nullable=False),
        sa.Column("output_tokens", sa.Integer, default=0, nullable=False),
        sa.Column("total_tokens", sa.Integer, default=0, nullable=False),
        sa.Column("cost_usd", sa.Integer, default=0, nullable=False),
        sa.Column("purpose", sa.String(32), default="summarize", nullable=False),
        sa.Column("policy_id", sa.Integer, default=0, nullable=False, index=True),
        sa.Column("status", sa.String(16), default="success", nullable=False),
        sa.Column("error_msg", sa.Text, default="", nullable=False),
        sa.Column("duration_ms", sa.Integer, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False, index=True),
    )

    # === 系统配置（key-value） ===
    op.create_table(
        "system_configs",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False, default=dict),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # === PolicySource 加 region / department / tags ===
    # 幂等 ADD COLUMN：兼容「DB 已被手工 ALTER 过列」的环境
    for col in ("region", "department", "tags"):
        try:
            with op.batch_alter_table("policy_sources") as batch:
                if col == "tags":
                    batch.add_column(sa.Column(col, sa.JSON, nullable=True))
                else:
                    batch.add_column(sa.Column(col, sa.String(64), nullable=True))
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            if "duplicate column" in msg or "already exists" in msg:
                # 列已存在（被手工 ALTER 过），跳过
                continue
            raise


def downgrade() -> None:
    with op.batch_alter_table("policy_sources") as batch:
        batch.drop_column("tags")
        batch.drop_column("department")
        batch.drop_column("region")
    op.drop_table("system_configs")
    op.drop_table("llm_usage_logs")
