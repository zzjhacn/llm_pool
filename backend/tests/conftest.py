"""pytest 公共夹具：在导入 app 之前注入测试环境变量，每个测试重置数据库。"""
import os
import tempfile
from pathlib import Path

# ---- 必须在导入 app 之前设置环境变量 ----
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["LLM_POOL_DB_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ["LLM_POOL_FORCE_MOCK"] = "1"  # 全程走 Mock 执行器，避免真实调用厂商
os.environ["LLM_POOL_GATEWAY_KEYS"] = "gpk-test,gpk-test2"
os.environ["LLM_POOL_AUTO_SEED"] = "1"
os.environ["LLM_POOL_ADMIN_USER"] = "admin"
os.environ["LLM_POOL_ADMIN_PASS"] = "admin123"
os.environ["LLM_POOL_SECRET"] = "test-secret"
os.environ["LLM_POOL_ESCAPE_MODEL_ID"] = "escape"
os.environ["LLM_POOL_SEED_FILE"] = str(
    Path(__file__).resolve().parent.parent / "seed.yaml"
)

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture
def client():
    """每个测试前清空并重建数据库，保证用例间隔离。"""
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_token(client):
    r = client.post("/admin/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture
def auth(client, admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


GW_AUTH = {"Authorization": "Bearer gpk-test"}
