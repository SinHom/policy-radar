"""add policy.advisory column

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-30 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # AI 业务解读(200字内,"这政策对企业怎么用")
    try:
        with op.batch_alter_table("policies") as batch:
            batch.add_column(sa.Column("advisory", sa.Text, nullable=True))
    except Exception as e:  # noqa: BLE001
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            return
        raise


def downgrade() -> None:
    with op.batch_alter_table("policies") as batch:
        batch.drop_column("advisory")
