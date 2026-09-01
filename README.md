# LLM Pool Gateway · 大模型统一池

一个把多家大模型平台（OpenAI / 通义千问 / 豆包 / Kimi / 本地 Ollama …）汇总成一个「池」并统一调度的网关。

> 例如，在百炼有多个免费额度的模型，每次“测试”要手动切换模型？运行本项目，维护模型后，可以自动调度，无需每次切换

- **统一 OpenAI 接口**：业务侧只对接一个 `/v1/chat/completions`，无需关心底层是哪家、哪个模型。
- **平台 / 模型 / 额度包管理**：维护各平台的 API 地址与 Key、每个模型的能力 / 价格 / 到期日，以及多个模型**共享**的一次性额度包（按 Token 或按次计费）。
- **智能路由**：根据请求内容、模型能力、余额、价格自动选最合适模型；额度耗尽自动熔断，无可用模型时降级到兜底模型。
- **运维控制台**：Vue3 管理页面，可视化 CRUD 与账本看板。

> 设计理念：把「能力矩阵 + 额度账本 + 路由决策」这一核心资产握在自己手里，协议适配（流式、重试、厂商 SDK）交给 LiteLLM。详见 [`design/`](design/)。

---

## 特性

| 需求                 | 实现                                        |
| ------------------ | ----------------------------------------- |
| 平台 API 地址 + Key 维护 | `Platform` 表；Key 仅存服务端，不下发                |
| 模型名 / 能力 / 价格 / 额度 | `Model` 表，价格挂模型、额度可挂共享包或模型独立额度            |
| 多模型共享总 Token 量     | `ResourcePackage` 共享账本，原子扣减               |
| 按 Token / 按次 计费    | `billing_type` 分叉扣减逻辑                     |
| 平台 / 模型 启用开关       | 双层开关；过期 / 额度耗尽 / **厂商侧 403 额度耗尽自动钉死为手动关闭(manual_disabled，sync 不复活)** 自动置否，亦可手动关              |
| 模型到期日期             | `expired_at`，路由硬过滤                        |
| 四因子自动路由            | 能力 → 余额 → 成本/质量打分 → 降级                    |
| 统一 OpenAI 接口       | `/v1/chat/completions`（含流式）+ `/v1/models` |

---

## 架构

```
┌────────────┐    OpenAI 风格请求    ┌──────────────────────────┐
│  业务客户端 │ ───────────────────▶ │  Model Pool Gateway       │
└────────────┘                       │  ┌────────────────────┐   │
                                      │  │ 统一接口 /v1/*      │   │
┌────────────┐   REST + 看板         │  ├────────────────────┤   │
│  Vue3 控制台 │ ◀──────────────────  │  │ 决策链路由 + 账本   │   │
└────────────┘                       │  ├────────────────────┤   │
                                      │  │ 执行器 (LiteLLM)   │   │
                                      │  └────────────────────┘   │
                                      │         │ 真实厂商调用      │
                                      └─────────┼──────────────────┘
                                                ▼
                                         OpenAI / 通义 / ...
```

后端：**Python + FastAPI + SQLAlchemy + LiteLLM**  
前端：**Vue3 + Vite + Element Plus + ECharts**（后端同源托管 `dist/`）

---

## 快速开始

### 方式一：本地运行（Mock 模式，不调真实厂商）

```bash
cd backend
export LLM_POOL_FORCE_MOCK=1 LLM_POOL_GATEWAY_KEYS=gpk-default
python3 -m uvicorn app.main:app --port 8000
# 管理后台：打开 http://127.0.0.1:8000  （默认 admin / admin123）

# 前端独立开发（热更新）：
cd backend/frontend && npm install && npm run dev   # http://localhost:5173
```

### 方式二：Docker（含前端构建）

```bash
cp .env.example .env   # 按需修改密钥
docker compose up --build
# 访问 http://localhost:8000
```

### 方式三：真实调用厂商

把 `backend/seed.yaml` 里各平台的 `api_key` 换成真实值，去掉 `LLM_POOL_FORCE_MOCK`，重启即可。

> 或者启动项目后，在管理页面维护

---

## 配置

所有配置通过环境变量注入，见 [`.env.example`](.env.example)。核心变量：

| 变量                         | 说明                       | 默认                                    |
| -------------------------- | ------------------------ | ------------------------------------- |
| `LLM_POOL_DB_URL`          | 数据库地址（SQLite / Postgres） | `sqlite:///./llm_pool.db`             |
| `LLM_POOL_ADMIN_USER/PASS` | 管理后台账号                   | `admin` / `admin123`                  |
| `LLM_POOL_SECRET`          | 管理 token 签名密钥            | 未设置则自动生成随机密钥（持久化于 `.llm_pool_secret`） |
| `LLM_POOL_CORS_ORIGINS`    | 跨域允许来源（逗号分隔）             | `*`                                   |
| `LLM_POOL_GATEWAY_KEYS`    | 网关 key（逗号分隔多个）           | `gpk-default`                         |
| `LLM_POOL_AUTO_SEED`       | 空库时导入种子                  | `1`                                   |
| `LLM_POOL_FORCE_MOCK`      | 设为 `1` 走 Mock 执行器        | 空                                     |
| `LLM_POOL_ESCAPE_MODEL_ID` | 兜底模型 id                  | `escape`                              |
| `LLM_POOL_ROUTE_STRATEGY` | 全局默认路由策略             | `balanced`（另含 lowest_cost / highest_quality / lowest_latency / expiring_soon） |
| `LLM_POOL_QUALITY_WEIGHT`  | balanced 下质量权重（0~1）  | `0.6`                                 |

---

## 接口速览

| 方法                  | 路径                                                   | 鉴权       | 说明                |
| ------------------- | ---------------------------------------------------- | -------- | ----------------- |
| GET                 | `/health`                                            | 无        | 健康检查              |
| POST                | `/v1/chat/completions`                               | 网关 key   | 统一对话（支持 `stream`） |
| GET                 | `/v1/models`                                         | 网关 key   | 列出可用模型            |
| POST                | `/admin/login`                                       | 无        | 获取管理 token        |
| GET/POST/PUT/DELETE | `/admin/platforms` `/admin/models` `/admin/packages` | 管理 token | CRUD              |
| GET                 | `/admin/ledger`                                      | 管理 token | 账本统计              |
| POST                | `/admin/sync`                                        | 管理 token | 依据当前状态刷新模型启停      |

### `model` 参数取值约定（重要）

对外 `/v1/chat/completions` 兼容 OpenAI 格式，但**对 `model` 参数做了缺省设计**：

- **不传 / 传空串 `""`** → 自动选择：交由决策链按「请求能力 → 平台/模型启用 → 到期 → 额度余额 → 成本/质量打分」自动挑一个最优模型（候选为空时降级到兜底模型 `escape`）。
  ```python
  # 例：不指定模型，自动路由
  llm = ChatOpenAI(base_url=BASE_URL, api_key=API_KEY, temperature=0)
  llm.invoke(msgs)
  ```
- **传具体值** → 锁定到该模型。可传两种等价值（决策链 pin 逻辑二者皆可）：
  1. **模型 `id`**（管理页「模型管理」第一列、或 `GET /v1/models` 返回的 `id`，如 `qwen-max`、`deepseek-self`）——**推荐**；
  2. **`provider_model` 串**（管理页「厂商模型」字段，如 `deepseek-chat`）。
  ```python
  # 例：锁定到某个模型（用 id 或 provider_model 均可）
  llm = ChatOpenAI(model="qwen-max", base_url=BASE_URL, api_key=API_KEY, temperature=0)
  llm.invoke(msgs)
  ```
  > 注意：传的值必须与页面上的 **`id`** 或 **`厂商模型`** 完全一致；**不是**「厂商键(provider)」字段。
- 若指定的模型当前**基础不可用**（不存在 / 平台关闭 / 已过期 / 额度耗尽），网关按「未传」处理**自动改选**可用模型，并通过响应头 `X-LLM-Pool-Pin-Dropped`（`not_found` / `unavailable`）告知降级；**仅当模型存在且基础可用、但能力不满足请求**（如要 `json_schema` 却指定仅 `json_object` 的模型）才返回 `400`。详见 [`design/04-决策链路由算法.md`](design/04-决策链路由算法.md)。

### 厂商键 `provider`（平台级属性）

`provider` 是**平台级**属性（管理页「平台管理 → 编辑 → 厂商键」），由平台端点形态决定，旗下所有模型默认继承：

- OpenAI 兼容端点（`api_base` 含 `compatible-mode` 或结尾 `/v1`）→ `openai`；
- 厂商原生端点才填 `dashscope` / `azure` / `bedrock` 等。

执行器拼装时优先用「模型上的可选覆盖」，否则继承「平台 provider」，最终发 `provider / 厂商模型` 给 LiteLLM（如 `openai/deepseek-v4-flash-0731`）。**选错 provider 会走错调用路径**——例如把 OpenAI 兼容端点设成 `dashscope`，会走 DashScope 原生 API、计费/额度路径不同，可能触发 403 `FreeTierOnly`。**漏配（空且平台也无）会导致 `LLM Provider NOT provided` 报错**。

> 排查直连/网关差异时，可单独用 `backend/tests/test_litellm_conn.py` 验证某个 `api_url/key/model/provider` 是否可用。

### 路由策略

全局默认策略由 `LLM_POOL_ROUTE_STRATEGY` 控制（默认 `balanced`），可选：`balanced`（质量/成本权衡）、`lowest_cost`、`highest_quality`、`lowest_latency`、`expiring_soon`（临近过期的模型优先消耗）。调用时也可在 `/v1/chat/completions`、`/v1/embeddings` 请求体传 `route_strategy` 字段临时覆盖。完整算法、pin 降级规则与可观测性见 [`design/04-决策链路由算法.md`](design/04-决策链路由算法.md)。

---

## 测试

```bash
cd backend
pip install -r requirements-dev.txt
python3 -m pytest
```

测试全程使用 Mock 执行器（不联网），覆盖鉴权、CRUD、能力路由、按 Token / 按次计费、额度耗尽熔断、兜底降级、手动关闭、流式等。

---

## 目录结构

```
llm_pool/
├── backend/                # 后端（FastAPI）+ 前端源码
│   ├── app/                # 应用代码
│   │   ├── models.py       # ORM 数据模型
│   │   ├── routing/        # 能力解析 + 决策链
│   │   ├── ledger/         # 额度账本 + 扣减 + 自动启停
│   │   ├── routers/        # /v1/* 与 /admin/*
│   │   ├── executor.py     # LiteLLM / Mock 执行器
│   │   └── main.py         # 应用入口
│   ├── frontend/           # Vue3 管理控制台
│   ├── seed.yaml           # 种子数据
│   └── tests/              # pytest 套件
├── design/                 # 设计文档（架构/数据模型/账本/决策链）
├── research/               # 同类项目调研
├── LICENSE                 # MIT
└── README.md
```

---

## License

[MIT](LICENSE) © 2026 Gray
