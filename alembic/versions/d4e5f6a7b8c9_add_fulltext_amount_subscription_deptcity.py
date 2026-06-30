"""add full_text_fetched_at + amount/deadline to policies; dept_codes/city_codes to subscriptions

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-30 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _safe_add(table: str, col: str, *args, **kwargs) -> None:
    """幂等 ADD COLUMN(被手工 ALTER 过则跳过)。"""
    try:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column(col, *args, **kwargs))
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            return
        raise


def upgrade() -> None:
    # policies: 全文抓取时间戳 + 金额/截止(摘要里)
    _safe_add("policies", "amount", sa.String(64), nullable=True)
    _safe_add("policies", "deadline", sa.String(64), nullable=True)
    _safe_add("policies", "full_text_fetched_at", sa.DateTime, nullable=True)

    # subscriptions: 委办 + 地市 多选(用 code 与 policy_sources.department/region 对齐)
    _safe_add("subscriptions", "dept_codes", sa.JSON, nullable=True)
    _safe_add("subscriptions", "city_codes", sa.JSON, nullable=True)

    op.create_index(
        "ix_policies_full_text_fetched_at", "policies", ["full_text_fetched_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_policies_full_text_fetched_at", table_name="policies")
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_column("city_codes")
        batch.drop_column("dept_codes")
    with op.batch_alter_table("policies") as batch:
        batch.drop_column("full_text_fetched_at")
        batch.drop_column("deadline")
        batch.drop_column("amount")
