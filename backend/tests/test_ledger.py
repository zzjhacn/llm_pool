"""账本扣减：按 Token / 按次计费、额度耗尽熔断、手动关闭、escape 兜底。"""
from tests.conftest import GW_AUTH


def _chat(client, messages, **kw):
    body = {"messages": messages, "stream": False, **kw}
    return client.post("/v1/chat/completions", headers=GW_AUTH, json=body)


def test_token_billing_deducts_and_ledger_grows(client, auth):
    r = _chat(client, [{"role": "user", "content": "Hello world"}], model="gpt-4o")
    assert r.status_code == 200
    pkg = client.get("/admin/packages/pkg-openai-paygo", headers=auth).json()
    assert pkg["used"] > 0
    led = client.get("/admin/ledger", headers=auth).json()
    assert led["total_calls"] >= 1
    assert led["total_cost"] > 0


def test_call_billing_deducts_one_unit(client, auth):
    # moonshot 平台默认关闭，先启用
    client.put("/admin/platforms/moonshot", headers=auth, json={"enabled": True})
    r = _chat(client, [{"role": "user", "content": "hi"}], model="kimi-call")
    assert r.status_code == 200
    pkg = client.get("/admin/packages/pkg-moonshot-call", headers=auth).json()
    assert pkg["used"] == 1.0  # 按次计费，每次扣 1
    led = client.get("/admin/ledger", headers=auth).json()
    assert any(b["model_id"] == "kimi-call" and b["units"] == 1.0 for b in led["by_model"])


def test_depletion_circuit_breaks_shared_package(client, auth):
    # 把 openai 包容量压到极小，一次调用即耗尽
    client.put("/admin/packages/pkg-openai-paygo", headers=auth, json={"capacity": 5, "used": 0})
    r = _chat(client, [{"role": "user", "content": "hello"}], model="gpt-4o")
    assert r.status_code == 200
    models = {m["id"]: m for m in client.get("/admin/models", headers=auth).json()}
    # 共享同一包的 gpt-4o 与 gpt-4o-mini 都应被自动置否，且非手动关闭
    assert models["gpt-4o"]["enabled"] is False
    assert models["gpt-4o"]["manual_disabled"] is False
    assert models["gpt-4o-mini"]["enabled"] is False


def test_manual_disable_excludes_model(client, auth):
    client.post("/admin/models/gpt-4o-mini/toggle?enabled=false", headers=auth)
    r = _chat(client, [{"role": "user", "content": "hi"}])
    assert r.json()["model"] != "gpt-4o-mini"


def test_escape_fallback_when_all_exhausted(client, auth):
    # 耗尽所有额度包，以及模型独立额度，仅 escape（无额度）始终可用
    for pid in ("pkg-aliyun-free", "pkg-openai-paygo", "pkg-moonshot-call"):
        client.put(f"/admin/packages/{pid}", headers=auth, json={"used": 999999999})
    client.put("/admin/models/deepseek-self", headers=auth, json={"quota_used": 5000000})
    r = _chat(client, [{"role": "user", "content": "hi"}])
    assert r.status_code == 200
    assert r.json()["model"] == "escape"
