"""SQLAlchemy 2.0 异步基础配置。

参考：
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- greenlet 是 Windows 上异步 SQLAlchemy 的必需依赖
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# 全局声明，main.py 启动时会覆盖
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。

    ⚠️ 不要在本项目任何地方调用 ``Base.metadata.create_all``。
    本项目以 alembic 迁移为唯一建表入口（见 ``entrypoint.sh``），
    任何 ``create_all`` 调用都会绕过迁移，造成 schema drift
    （已发生过一次：policy_sources.region 缺列）。
    新增/修改表结构 → 改 ``alembic/versions/`` 下的迁移文件。
    """


# Lint-style 护栏：如果有人误调 create_all，提示正确做法
_orig_create_all = Base.metadata.create_all


def _create_all_blocked(*args, **kwargs):  # pragma: no cover
    raise RuntimeError(
        "Base.metadata.create_all 被禁止使用。\n"
        "本项目以 alembic 迁移为唯一建表入口。\n"
        "新增表/列 → 在 alembic/versions/ 写新迁移文件。\n"
        "现有 schema 漂移 → alembic revision --autogenerate 生成修复迁移。"
    )


Base.metadata.create_all = _create_all_blocked  # type: ignore[assignment]
"""全局拦截 create_all 调用。任何代码（包括 ORM 自动调用）尝试建表都会抛错。"""


def _default_db_url() -> str:
    """默认 SQLite 路径：项目根 / data / policy_radar.db"""
    # python/models/base.py → python/models/ → python/ → 项目根
    project_root = Path(__file__).resolve().parent.parent.parent
    db_path = project_root / "data" / "policy_radar.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


def make_engine(url: str | None = None, *, echo: bool = False):
    """创建异步引擎。

    SQLite 需要 `check_same_thread=False`，PostgreSQL 不需要。
    """
    db_url = url or os.environ.get("DATABASE_URL") or _default_db_url()
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_async_engine(db_url, echo=echo, connect_args=connect_args, future=True)


def init_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """初始化全局 session 工厂（在 main.py 启动时调用一次）。"""
    global AsyncSessionLocal
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return AsyncSessionLocal


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """异步上下文管理器：自动 commit / rollback / close。

    用法：
        async with get_session() as session:
            session.add(obj)
    """
    if AsyncSessionLocal is None:
        raise RuntimeError("AsyncSessionLocal 未初始化，请先调用 init_session_factory()")
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
