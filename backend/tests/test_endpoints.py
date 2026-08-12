"""端点契约：健康检查、未知 API 路径返回标准 404 JSON（而非 SPA HTML）。"""
from tests.conftest import GW_AUTH


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_v1_path_returns_json_404(client):
    r = client.get("/v1/does-not-exist", headers=GW_AUTH)
    assert r.status_code == 404
    assert r.headers.get("content-type", "").startswith("application/json")


def test_unknown_admin_path_returns_json_404(client, auth):
    r = client.get("/admin/does-not-exist", headers=auth)
    assert r.status_code == 404
    assert r.headers.get("content-type", "").startswith("application/json")
