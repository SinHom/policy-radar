"""add audit_logs table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-27 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(64), nullable=False, index=True),
        sa.Column("action", sa.String(32), nullable=False, index=True),
        sa.Column("target_type", sa.String(32), nullable=False, default=""),
        sa.Column("target_id", sa.String(64), nullable=False, default=""),
        sa.Column("detail", sa.Text, nullable=False, default=""),
        sa.Column("ip", sa.String(64), nullable=False, default=""),
        sa.Column("ua", sa.String(256), nullable=False, default=""),
        sa.Column("status", sa.String(16), nullable=False, default="success"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
