import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import AUTO_SEED, FRONTEND_DIST, SEED_FILE, ADMIN_USERNAME, ADMIN_PASSWORD, GATEWAY_API_KEYS
from .db import SessionLocal, init_db
from .routers import admin, openai
from .seed import load_seed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("llm_pool")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：建表 + 空库时导入种子
    init_db()
    if AUTO_SEED and os.path.exists(SEED_FILE):
        from . import models as _m

        db = SessionLocal()
        try:
            if db.query(_m.Platform).count() == 0:
                stats = load_seed(db, SEED_FILE)
                logger.info("已导入种子: %s", stats)
        finally:
            db.close()
    # 安全自检：使用默认弱口令/弱 key 时给出明确告警
    if ADMIN_PASSWORD == "admin123" and ADMIN_USERNAME == "admin":
        logger.warning("⚠️ 安全提醒：正在使用默认管理员口令 admin/admin123，生产环境请通过 LLM_POOL_ADMIN_PASS 修改。")
    if "gpk-default" in GATEWAY_API_KEYS:
        logger.warning("⚠️ 安全提醒：正在使用默认网关 key 'gpk-default'，请通过 LLM_POOL_GATEWAY_KEYS 修改。")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Model Pool Gateway", version="0.1.0", lifespan=lifespan)
    # CORS：管理台与网关同源部署；跨域场景用 Bearer 头鉴权（非 cookie），无需 credentials。
    # allow_credentials 必须为 False，否则与 allow_origins=["*"] 组合在浏览器侧无效且存在隐患。
    cors_origins = os.getenv("LLM_POOL_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # API 路由优先注册，确保不会被后面的 SPA catch-all 吞掉
    app.include_router(openai.router)
    app.include_router(admin.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # 同源提供前端（若存在 dist）：静态文件直接返回，其余路径回退 index.html
    # （SPA history 模式）。API 路由已在前面注册，优先匹配。
    if os.path.isdir(FRONTEND_DIST):

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            # 已知 API 前缀的未知子路径不应回退到 SPA，返回标准 404
            if full_path.startswith(("v1/", "admin/")):
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Not Found")
            fp = os.path.join(FRONTEND_DIST, full_path)
            if os.path.isfile(fp):
                return FileResponse(fp)
            return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    return app


app = create_app()
