#!/bin/bash
# Docker entrypoint: 先跑 alembic 升级 DB，再 exec uvicorn
# ⚠️ 严禁用 Base.metadata.create_all — 本项目以 alembic 为唯一建表入口
set -e
echo "=== Running alembic upgrade head ==="
alembic upgrade head
echo "=== Alembic done. Starting uvicorn ==="
exec "$@"
