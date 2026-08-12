# 模型池网关 (Model Pool Gateway)

多平台大模型统一池：维护平台/模型/额度包，提供 OpenAI 风格统一接口，按能力+余额+定价自动路由。

## 技术栈
- 后端：Python 3.12 + FastAPI + SQLAlchemy + LiteLLM(执行器，缺失时自动走 Mock)
- 前端：Vue 3 + Vite + Element Plus + ECharts + Pinia + Axios
- 存储：SQLite（账本事务原子扣减）

## 运行

### 后端
```bash
cd backend
export LLM_POOL_DB_URL="sqlite:///$PWD/llm_pool.db"
export LLM_POOL_GATEWAY_KEYS="gpk-default"      # 客户端调 /v1/* 用的网关 key
export LLM_POOL_ADMIN_USER=admin LLM_POOL_ADMIN_PASS=admin123
export LLM_POOL_FORCE_MOCK=1                     # 本地无真实厂商 key 时走 Mock
# 真实调用：去掉 FORCE_MOCK，并把 seed.yaml 里的 api_key 换成真实 key
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
启动时空库自动导入 `seed.yaml`（仅创建缺失记录，不覆盖手动修改）。

### 前端
```bash
cd backend/frontend
npm install
npm run dev      # 开发 http://localhost:5173（代理 /admin、/v1 到 8000）
# 或 npm run build 后由后端同源提供 dist/
```

## 接口
- 业务面（网关 key 鉴权）：`POST /v1/chat/completions`、`GET /v1/models`
- 管理面（登录后 token 鉴权）：`/admin/login`、`/admin/platforms`、`/admin/models`、`/admin/packages`、`/admin/ledger`、`/admin/sync`、`POST /admin/models/{id}/toggle`

## 验证（测试）
```bash
cd backend
pip install -r requirements-dev.txt
python3 -m pytest          # 30+ 用例：鉴权/CRUD/路由/计费/熔断/降级/流式，全程 Mock 不联网
```

## 设计文档
见 `../design/`：01 总体架构、02 数据模型、03 账本计费、04 决策链。
