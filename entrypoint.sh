#!/bin/bash
# Docker entrypoint: 先跑 alembic 升级 DB，再 exec uvicorn
set -e
echo "=== Running alembic upgrade head ==="
alembic upgrade head
echo "=== Alembic done. Starting uvicorn ==="
exec "$@"
