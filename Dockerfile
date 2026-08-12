# syntax=docker/dockerfile:1

# ---------- 1. 构建前端 ----------
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY backend/frontend/package.json backend/frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY backend/frontend/ ./
RUN npm run build

# ---------- 2. 运行后端 ----------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LLM_POOL_HOST=0.0.0.0 \
    LLM_POOL_PORT=8000

WORKDIR /app

# 依赖先装（利用层缓存）
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY backend/ /app/
# 把构建好的前端产物放进 backend/frontend/dist，由后端同源托管
COPY --from=frontend-build /build/dist /app/frontend/dist

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host $LLM_POOL_HOST --port $LLM_POOL_PORT"]
