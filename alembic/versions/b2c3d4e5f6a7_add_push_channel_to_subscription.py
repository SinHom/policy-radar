"""add push_channel + push_config to subscriptions

Revision ID: b2c3d4e5f6a7
Revises: 8a1b2c3d4e5f
Create Date: 2026-06-27 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "b2c3d4e5f6a7"
down_revision = "8a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch:
        batch.add_column(sa.Column("push_channel", sa.String(16), nullable=False, server_default="mock"))
        batch.add_column(sa.Column("push_config", sa.JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_column("push_config")
        batch.drop_column("push_channel")
