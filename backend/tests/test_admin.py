"""管理面 CRUD 与模型启停。"""


def test_platform_crud(client, auth):
    r = client.post(
        "/admin/platforms",
        headers=auth,
        json={"id": "p1", "name": "P1", "api_base": "https://x.example/v1", "api_key": "sk-x", "enabled": True},
    )
    assert r.status_code == 200
    assert client.get("/admin/platforms/p1", headers=auth).status_code == 200
    r = client.put("/admin/platforms/p1", headers=auth, json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert client.delete("/admin/platforms/p1", headers=auth).status_code == 200
    assert client.get("/admin/platforms/p1", headers=auth).status_code == 404


def test_platform_duplicate(client, auth):
    client.post("/admin/platforms", headers=auth, json={"id": "dup", "name": "D", "api_base": "https://x", "api_key": "k"})
    r = client.post("/admin/platforms", headers=auth, json={"id": "dup", "name": "D", "api_base": "https://x", "api_key": "k"})
    assert r.status_code == 409


def test_model_create_validation(client, auth):
    # package 不存在
    r = client.post(
        "/admin/models",
        headers=auth,
        json={"id": "m1", "platform_id": "openai", "name": "M", "provider_model": "x", "package_id": "nope"},
    )
    assert r.status_code == 400
    # platform 不存在
    r = client.post(
        "/admin/models",
        headers=auth,
        json={"id": "m1", "platform_id": "nope", "name": "M", "provider_model": "x"},
    )
    assert r.status_code == 400


def test_model_create_and_delete(client, auth):
    r = client.post(
        "/admin/models",
        headers=auth,
        json={
            "id": "m1",
            "platform_id": "openai",
            "name": "M1",
            "provider_model": "gpt-4o",
            "capabilities": ["chat"],
            "package_id": "pkg-openai-paygo",
        },
    )
    assert r.status_code == 200
    assert client.delete("/admin/models/m1", headers=auth).status_code == 200


def test_toggle_model_manual_disable(client, auth):
    r = client.post("/admin/models/gpt-4o-mini/toggle?enabled=false", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["manual_disabled"] is True
    assert body["enabled"] is False
    # 重新启用
    r = client.post("/admin/models/gpt-4o-mini/toggle?enabled=true", headers=auth)
    assert r.json()["manual_disabled"] is False
    assert r.json()["enabled"] is True


def test_package_crud(client, auth):
    r = client.post(
        "/admin/packages",
        headers=auth,
        json={"id": "pkg-x", "name": "X", "unit": "token", "capacity": 1000},
    )
    assert r.status_code == 200
    assert r.json()["balance"] == 1000.0
    r = client.put("/admin/packages/pkg-x", headers=auth, json={"capacity": 500, "used": 100})
    assert r.status_code == 200
    assert r.json()["balance"] == 400.0
    assert client.delete("/admin/packages/pkg-x", headers=auth).status_code == 200


def test_update_model_to_none_quota_no_integrity_error(client, auth):
    """编辑模型切到「无额度」时前端会传 quota_used=null，后端必须归一为 0 而非触发 NOT NULL 冲突。"""
    create = client.post(
        "/admin/models",
        headers=auth,
        json={"id": "m-none", "platform_id": "openai", "name": "M", "provider_model": "gpt-4o"},
    )
    assert create.status_code == 200
    # 切到无额度且显式传 quota_used=null（复现线上报错场景）
    r = client.put("/admin/models/m-none", headers=auth, json={"quota_used": None, "package_id": None, "quota_capacity": None})
    assert r.status_code == 200
    assert r.json()["quota_source"] == "none"
    assert r.json()["quota_used"] == 0.0
    # 切到共享包同样传 null 也不应报错
    client.post("/admin/packages", headers=auth, json={"id": "pkg-none", "name": "P", "unit": "token", "capacity": 100})
    r2 = client.put("/admin/models/m-none", headers=auth, json={"package_id": "pkg-none", "quota_used": None})
    assert r2.status_code == 200
    assert r2.json()["quota_source"] == "package"
    client.delete("/admin/packages/pkg-none", headers=auth)
    client.delete("/admin/models/m-none", headers=auth)

