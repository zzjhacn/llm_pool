from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DB_URL

connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()


def init_db() -> None:
    # 确保模型已注册
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)
    _migrate_columns()


def _migrate_columns() -> None:
    """为已存在的库补齐新增列（SQLite 的 create_all 不会 ALTER 已有表）。

    provider 已从「模型级」上移到「平台级」：每个平台有自己的 LiteLLM 厂商键，
    模型默认继承；模型上的 provider 仅作为可选覆盖。
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    models_cols = {c["name"] for c in inspector.get_columns("models")}
    plat_cols = {c["name"] for c in inspector.get_columns("platforms")}
    with engine.begin() as conn:
        # 模型上的 provider 列（历史上曾作为主字段）：保留为可选覆盖列
        if "provider" not in models_cols:
            conn.execute(text("ALTER TABLE models ADD COLUMN provider VARCHAR"))

        # 平台上的 provider 列（新增，作为权威来源）
        if "provider" not in plat_cols:
            conn.execute(text("ALTER TABLE platforms ADD COLUMN provider VARCHAR"))
            # 由该平台旗下模型的 provider 众数回填；无模型则默认 openai
            for (pid,) in conn.execute(text("SELECT id FROM platforms")).fetchall():
                row = conn.execute(
                    text(
                        "SELECT provider FROM models WHERE platform_id=:p AND provider IS NOT NULL "
                        "GROUP BY provider ORDER BY COUNT(*) DESC LIMIT 1"
                    ),
                    {"p": pid},
                ).fetchone()
                val = row[0] if row else "openai"
                conn.execute(text("UPDATE platforms SET provider=:v WHERE id=:p"), {"v": val, "p": pid})
            # 清空模型上的 provider，使其统一继承平台（修复曾误设在模型上的厂商键，如 dashscope）
            conn.execute(text("UPDATE models SET provider=NULL WHERE provider IS NOT NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
