"""Alembic env: 完全自管 DATABASE_URL，不依赖 alembic.ini 里的 url。"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from python.models import Base  # noqa: E402
from python.models.base import _default_db_url  # noqa: E402

config = context.config

# 用环境变量或默认 URL 完全覆盖 alembic.ini 里的 sqlalchemy.url
db_url = os.environ.get("DATABASE_URL") or _default_db_url()
# 异步 driver → 同步 driver（alembic 跑迁移用同步）
db_url_sync = (
    db_url.replace("sqlite+aiosqlite", "sqlite", 1)
    if db_url.startswith("sqlite+aiosqlite")
    else db_url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    if db_url.startswith("postgresql+asyncpg")
    else db_url
)
config.set_main_option("sqlalchemy.url", db_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
