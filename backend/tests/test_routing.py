"""决策链路由：能力解析 → 硬过滤 → 打分选中 / 兜底。"""
from tests.conftest import GW_AUTH


def _chat(client, messages, **kw):
    body = {"messages": messages, "stream": False, **kw}
    return client.post("/v1/chat/completions", headers=GW_AUTH, json=body)


def test_code_request_selects_code_capable_model(client):
    r = _chat(client, [{"role": "user", "content": "请用 Python 写一个快速排序算法"}])
    assert r.status_code == 200
    sel = r.json()["model"]
    # 具备 code 能力的模型集合；escape 仅 chat，必被能力过滤排除
    assert sel in ("qwen-max", "gpt-4o", "gpt-4o-mini", "deepseek-self")


def test_vision_request_selects_vision_capable_model(client):
    r = _chat(client, [{"role": "user", "content": "请描述这张图片里的物体"}])
    assert r.status_code == 200
    sel = r.json()["model"]
    assert sel in ("qwen-vl-max", "gpt-4o", "gpt-4o-mini")


def test_pinned_model(client):
    r = _chat(client, [{"role": "user", "content": "hi"}], model="gpt-4o-mini")
    assert r.json()["model"] == "gpt-4o-mini"


def test_pinned_unavailable_returns_400(client):
    r = _chat(client, [{"role": "user", "content": "hi"}], model="does-not-exist")
    assert r.status_code == 400


def test_lowest_cost_strategy_picks_cheapest(client):
    r = _chat(client, [{"role": "user", "content": "hi"}], route_strategy="lowest_cost")
    # 全 chat 能力候选里 gpt-4o-mini 单价最低
    assert r.json()["model"] == "gpt-4o-mini"


def test_expiring_soon_prefers_nearest_expiry(client, auth):
    # 给两个 chat 候选设置不同到期时间，其余 chat 候选无到期（排最后）
    client.put("/admin/models/gpt-4o-mini", headers=auth, json={"expired_at": "2026-08-20T00:00:00"})
    client.put("/admin/models/gpt-4o", headers=auth, json={"expired_at": "2026-09-01T00:00:00"})
    r = _chat(client, [{"role": "user", "content": "hi"}], route_strategy="expiring_soon")
    # 临近过期的 gpt-4o-mini(08-20) 应先于 gpt-4o(09-01)、qwen-max(12-31) 及无到期者被选中
    assert r.json()["model"] == "gpt-4o-mini"


def test_expired_model_excluded(client, auth):
    client.put("/admin/models/gpt-4o-mini", headers=auth, json={"expired_at": "2020-01-01"})
    ids = [m["id"] for m in client.get("/v1/models", headers=GW_AUTH).json()["data"]]
    assert "gpt-4o-mini" not in ids


def test_disabled_platform_excluded(client, auth):
    client.put("/admin/platforms/openai", headers=auth, json={"enabled": False})
    ids = [m["id"] for m in client.get("/v1/models", headers=GW_AUTH).json()["data"]]
    assert "gpt-4o" not in ids
    assert "gpt-4o-mini" not in ids
