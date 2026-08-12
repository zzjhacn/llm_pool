"""鉴权：网关 key（业务面）与管理 token（管理面）分离。"""


def test_v1_models_requires_gateway_key(client):
    assert client.get("/v1/models").status_code == 401


def test_v1_models_with_gateway_key(client):
    r = client.get("/v1/models", headers={"Authorization": "Bearer gpk-test"})
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["data"]]
    assert "gpt-4o" in ids
    assert "escape" in ids


def test_admin_requires_token(client):
    assert client.get("/admin/models").status_code == 401


def test_login_wrong_password(client):
    r = client.post("/admin/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_ok_and_token_works(client):
    r = client.post("/admin/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert token
    assert client.get("/admin/models", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_second_gateway_key_accepted(client):
    # 配置里给了两个 key，gpk-test2 也应放行
    assert client.get("/v1/models", headers={"Authorization": "Bearer gpk-test2"}).status_code == 200
