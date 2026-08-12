# Token 池账本与计费设计

## 1. 资源量泛化

R2 的"总Token量"泛化为"总资源量"，由 `billing_type` 决定单位：
- **token**：单位为 token 数，按实际用量扣减
- **call**：单位为 次数，每次请求扣 1

## 2. 扣减规则

- **按Token**：用量 = `prompt_tokens + completion_tokens`（取自 LiteLLM 返回的 `usage`）。
  - 成本 = `prompt_tokens/1000 × input_price_per_1k + completion_tokens/1000 × output_price_per_1k`
  - 包.used += (prompt_tokens + completion_tokens)
- **按次**：每次成功请求 包.used += 1（或模型独立额度 .used += 1）；成本 = `price_per_call`（与 token 多少无关）
- **共享包**：`used` 是跨模型共享的单一计数器，任一模型消费都累加。
- **模型独立额度（self）**：扣减落在模型自身的 `quota_used`，仅影响本模型。
- **无额度（none）**：不扣减。

## 3. 原子性

- 扣减在 SQLite 事务内完成，避免并发超卖。
- 时机：流式场景在**流结束、拿到 usage** 后扣减（per-token）；per-call 也在请求成功（HTTP 200）后扣减，避免失败请求误扣。
- 失败请求（非 200 / 异常）不扣减，但记入审计日志。

## 4. 耗尽与熔断

- `balance = capacity - used`；当 `used >= capacity` → 包耗尽。
- 决策链硬过滤：额度来源非 none 且 `balance <= 0` 的模型不参与路由（视为不可用）。
- **熔断分两支**（锁定决策④）：
  - 共享包耗尽 → 级联禁用该包下**全部**模型；
  - 模型独立额度耗尽 → 仅停用**自己**（无兄弟可级联）。
- 可选：余额低于阈值（如 < 5%）触发告警。

## 5. 到期与余额的关系（锁定决策①）

- 到期**仅模型层**：`model.expired_at` 过期的模型直接出局，与其所在包的余额无关。
- 包本身无到期；包随"旗下所有模型均过期 或 包耗尽"而实际失效。
- 共享包内某模型过期，不影响其他未过期模型继续消费同一包的余额。

## 6. 计费与统计

- 每次请求落一条 usage 记录（model_id, package_id, tokens_in/out 或 calls, cost, ts, ok）。
- `/admin/ledger` 提供：各包余额、累计成本、各模型命中次数、命中率，用于成本核算与路由调优。
