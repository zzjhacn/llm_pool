"""独立额度（模型自带）与额度来源校验：self / package / none。"""
from tests.conftest import GW_AUTH


def _chat(client, messages, **kw):
    body = {"messages": messages, "stream": False, **kw}
    return client.post("/v1/chat/completions", headers=GW_AUTH, json=body)


def _mk_self(client, auth, mid, billing_type="token", capacity=100, capabilities=None):
    return client.post(
        "/admin/models",
        headers=auth,
        json={
            "id": mid,
            "platform_id": "aliyun",
            "name": mid,
            "provider_model": mid,
            "capabilities": capabilities or ["chat"],
            "billing_type": billing_type,
            "price_per_call": 0.5 if billing_type == "call" else 0.0,
            "price_input": 0.01,
            "price_output": 0.02,
            "quality_tier": 3,
            "latency_tier": 3,
            "context_window": 8000,
            "package_id": None,
            "quota_capacity": capacity,
            "quota_used": 0,
            "enabled": True,
        },
    )


def test_self_quota_token_deducts_inline(client, auth):
    r = _mk_self(client, auth, "self-tok", "token", 100, ["chat", "code"])
    assert r.status_code == 200, r.text
    assert r.json()["quota_source"] == "self"
    assert r.json()["quota_balance"] == 100.0
    _chat(client, [{"role": "user", "content": "hi"}], model="self-tok")
    m = client.get("/admin/models/self-tok", headers=auth).json()
    assert m["quota_used"] > 0  # 扣在模型自身，而非共享包


def test_self_quota_call_deducts_one_unit(client, auth):
    r = _mk_self(client, auth, "self-call", "call", 10, ["chat"])
    assert r.status_code == 200
    _chat(client, [{"role": "user", "content": "hi"}], model="self-call")
    m = client.get("/admin/models/self-call", headers=auth).json()
    assert m["quota_used"] == 1.0  # 按次计费，每次扣 1
    led = client.get("/admin/ledger", headers=auth).json()
    assert any(b["model_id"] == "self-call" and b["units"] == 1.0 for b in led["by_model"])


def test_self_quota_exhaustion_disables_only_self(client, auth):
    # 极小独立额度，一次调用即耗尽；应仅停用自己，不级联其他模型
    r = _mk_self(client, auth, "self-tiny", "token", 5, ["chat"])
    assert r.status_code == 200
    _chat(client, [{"role": "user", "content": "hello"}], model="self-tiny")
    m = client.get("/admin/models/self-tiny", headers=auth).json()
    assert m["enabled"] is False
    assert m["manual_disabled"] is False
    assert m["quota_balance"] == 0.0
    # 不应影响到共享包里的其它模型（如 gpt-4o-mini）
    others = {x["id"]: x for x in client.get("/admin/models", headers=auth).json()}
    assert others["gpt-4o-mini"]["enabled"] is True


def test_sync_recomputes_self_exhaustion(client, auth):
    _mk_self(client, auth, "self-sync", "token", 5, ["chat"])
    _chat(client, [{"role": "user", "content": "hello"}], model="self-sync")
    m = client.get("/admin/models/self-sync", headers=auth).json()
    assert m["enabled"] is False  # 扣减时即时熔断
    # 补充额度后同步应恢复启用
    client.put("/admin/models/self-sync", headers=auth, json={"quota_used": 0})
    client.post("/admin/sync", headers=auth)
    m = client.get("/admin/models/self-sync", headers=auth).json()
    assert m["enabled"] is True


def test_conflict_package_and_self_quota_rejected(client, auth):
    r = client.post(
        "/admin/models",
        headers=auth,
        json={
            "id": "bad-model",
            "platform_id": "aliyun",
            "name": "bad",
            "provider_model": "bad",
            "package_id": "pkg-aliyun-free",
            "quota_capacity": 100,  # 与 package_id 冲突
        },
    )
    assert r.status_code == 400
    assert "冲突" in r.json()["detail"]


def test_package_billing_mismatch_rejected(client, auth):
    r = client.post(
        "/admin/models",
        headers=auth,
        json={
            "id": "mismatch",
            "platform_id": "aliyun",
            "name": "mismatch",
            "provider_model": "mismatch",
            "billing_type": "call",  # pkg-aliyun-free 是 token 单位
            "package_id": "pkg-aliyun-free",
        },
    )
    assert r.status_code == 400
    assert "计费" in r.json()["detail"]
