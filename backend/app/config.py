import os

# backend/app → backend
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(APP_DIR)

DB_URL = os.getenv(
    "LLM_POOL_DB_URL", f"sqlite:///{os.path.join(BACKEND_DIR, 'llm_pool.db')}"
)

# 网关 key：客户端调 /v1/* 用。多个用逗号分隔。
GATEWAY_API_KEYS = [
    k.strip() for k in os.getenv("LLM_POOL_GATEWAY_KEYS", "gpk-default").split(",") if k.strip()
]

# 管理面登录凭据
ADMIN_USERNAME = os.getenv("LLM_POOL_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("LLM_POOL_ADMIN_PASS", "admin123")

# 管理 token 签名密钥
# 安全：若未显式配置、或仍为公开默认值，则自动生成随机密钥并持久化到 .llm_pool_secret
# （容器/本地可读写目录），重启后复用 —— 避免“默认密钥可被任何人伪造 admin token”的风险。
_KNOWN_DEFAULT_SECRETS = {
    "llm-pool-dev-secret-change-me",
    "change-me",
    "change-me-to-a-long-random-secret",
}


def _resolve_secret() -> str:
    env_val = os.getenv("LLM_POOL_SECRET")
    if env_val and env_val not in _KNOWN_DEFAULT_SECRETS:
        return env_val
    secret_file = os.path.join(BACKEND_DIR, ".llm_pool_secret")
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r") as f:
                saved = f.read().strip()
                if saved:
                    return saved
    except OSError:
        pass
    import secrets as _secrets

    generated = _secrets.token_hex(32)
    try:
        with open(secret_file, "w") as f:
            f.write(generated)
        os.chmod(secret_file, 0o600)
    except OSError:
        pass  # 目录不可写时退化为本次进程内有效（重启后重新生成，旧 token 失效）
    return generated


SECRET = _resolve_secret()

# 路由策略与打分权重
DEFAULT_ROUTE_STRATEGY = os.getenv("LLM_POOL_ROUTE_STRATEGY", "balanced")  # balanced|lowest_cost|highest_quality|lowest_latency|expiring_soon
QUALITY_WEIGHT = float(os.getenv("LLM_POOL_QUALITY_WEIGHT", "0.6"))  # balanced 策略下质量权重
# 兜底 escape 模型：候选为空时，若配置了则强制路由到它（仍需满足启用+余额）
ESCAPE_MODEL_ID = os.getenv("LLM_POOL_ESCAPE_MODEL_ID", "") or None

# 启动时空库是否自动导入种子
AUTO_SEED = os.getenv("LLM_POOL_AUTO_SEED", "1") == "1"
SEED_FILE = os.getenv("LLM_POOL_SEED_FILE", os.path.join(BACKEND_DIR, "seed.yaml"))

# 前端 dist 挂载路径（存在则同源提供管理控制台）
FRONTEND_DIST = os.getenv("LLM_POOL_FRONTEND_DIST", os.path.join(BACKEND_DIR, "frontend", "dist"))
