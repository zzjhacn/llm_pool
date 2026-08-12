#!/usr/bin/env bash
# 启动模型池网关（开发模式；生产/Docker 可用 PYTHON=python3 覆盖）
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
export LLM_POOL_DB_URL="${LLM_POOL_DB_URL:-sqlite:///$PWD/llm_pool.db}"
export LLM_POOL_GATEWAY_KEYS="${LLM_POOL_GATEWAY_KEYS:-gpk-default}"
export LLM_POOL_ADMIN_USER="${LLM_POOL_ADMIN_USER:-admin}"
export LLM_POOL_ADMIN_PASS="${LLM_POOL_ADMIN_PASS:-admin123}"
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
