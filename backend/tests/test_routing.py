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


# ---------------- 结构化输出能力过滤 ----------------
def test_json_schema_request_selects_json_schema_capable(client):
    r = _chat(
        client,
        [{"role": "user", "content": "请回答一个问题"}],
        response_format={"type": "json_schema", "json_schema": {"name": "GroundedAnswer"}},
    )
    assert r.status_code == 200
    sel = r.json()["model"]
    # 仅 gpt-4o / gpt-4o-mini 声明了 json_schema；qwen/deepseek/escape 均不具备
    assert sel in ("gpt-4o", "gpt-4o-mini")


def test_json_object_request_excludes_chat_only_escape(client):
    r = _chat(
        client,
        [{"role": "user", "content": "请回答一个问题"}],
        response_format={"type": "json_object"},
    )
    assert r.status_code == 200
    sel = r.json()["model"]
    # escape 仅 chat，必被结构化能力过滤排除
    assert sel != "escape"


def test_json_schema_no_capable_model_returns_400(client, auth):
    # 撤销 gpt-4o 与 gpt-4o-mini 的 json_schema 能力，使池中无 json_schema 模型
    for mid, caps in (
        ("gpt-4o", ["chat", "code", "vision", "function_calling", "json_object"]),
        ("gpt-4o-mini", ["chat", "code", "vision", "function_calling", "json_object"]),
    ):
        client.put(f"/admin/models/{mid}", headers=auth, json={"capabilities": caps})
    r = _chat(
        client,
        [{"role": "user", "content": "请回答"}],
        response_format={"type": "json_schema", "json_schema": {"name": "X"}},
    )
    assert r.status_code == 400
    assert "json_schema" in r.json()["detail"]


def test_pinned_model_lacking_json_schema_returns_400(client):
    # qwen-max 仅 json_object，无 json_schema；强一致请求锁定它应早失败
    r = _chat(
        client,
        [{"role": "user", "content": "请回答"}],
        model="qwen-max",
        response_format={"type": "json_schema", "json_schema": {"name": "X"}},
    )
    assert r.status_code == 400
    assert "json_schema" in r.json()["detail"]


def test_tools_request_requires_function_calling(client):
    r = _chat(
        client,
        [{"role": "user", "content": "请回答"}],
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
    )
    assert r.status_code == 200
    sel = r.json()["model"]
    # 仅 gpt-4o / gpt-4o-mini 声明 function_calling
    assert sel in ("gpt-4o", "gpt-4o-mini")


# ---------------- embeddings 能力过滤 ----------------
def test_embeddings_request_selects_embedding_capable_model(client):
    # seed 中仅 text-embedding-3-small 声明了 embedding 能力，应被选中
    r = client.post(
        "/v1/embeddings",
        headers=GW_AUTH,
        json={"input": "你好世界"},
    )
    assert r.status_code == 200
    assert r.json()["model"] == "text-embedding-3-small"


def test_embeddings_pinned_requires_embedding_capable(client):
    # 锁定到仅 chat 的 qwen-max，缺 embedding 能力应早失败 400
    r = client.post(
        "/v1/embeddings",
        headers=GW_AUTH,
        json={"model": "qwen-max", "input": "你好世界"},
    )
    assert r.status_code == 400
    assert "embedding" in r.json()["detail"]


def test_embeddings_no_capable_model_returns_400(client, auth):
    # 撤销 text-embedding-3-small 的 embedding 能力，使池中无 embedding 模型
    client.put(
        "/admin/models/text-embedding-3-small",
        headers=auth,
        json={"capabilities": ["chat"]},
    )
    r = client.post("/v1/embeddings", headers=GW_AUTH, json={"input": "你好世界"})
    assert r.status_code == 400
    assert "embedding" in r.json()["detail"]

