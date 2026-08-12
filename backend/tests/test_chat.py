"""统一 OpenAI 接口：非流式结构、流式 SSE、usage 透传。"""
from tests.conftest import GW_AUTH


def test_non_stream_returns_openai_shape(client):
    r = client.post(
        "/v1/chat/completions",
        headers=GW_AUTH,
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["object"] == "chat.completion"
    assert d["choices"][0]["message"]["role"] == "assistant"
    assert d["usage"]["total_tokens"] > 0


def test_stream_returns_sse_with_done(client):
    r = client.post(
        "/v1/chat/completions",
        headers=GW_AUTH,
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    assert r.status_code == 200
    body = r.text
    assert "data: [DONE]" in body
    # 至少有一条 chunk 携带 usage
    usage_chunks = [l for l in body.splitlines() if l.startswith("data:") and "usage" in l]
    assert usage_chunks


def test_stream_deducts_ledger(client, auth):
    before = client.get("/admin/ledger", headers=auth).json()["total_calls"]
    client.post(
        "/v1/chat/completions",
        headers=GW_AUTH,
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    after = client.get("/admin/ledger", headers=auth).json()["total_calls"]
    assert after == before + 1


def test_empty_model_auto_selects(client):
    # model 不传或空串应自动选择，并回显被选中的模型 id
    for body in [{"model": ""}, {}]:
        r = client.post(
            "/v1/chat/completions",
            headers=GW_AUTH,
            json={"messages": [{"role": "user", "content": "hi"}], "stream": False, **body},
        )
        assert r.status_code == 200
        assert r.json()["model"]  # 自动选中后回显 id


def test_pin_by_id_locks_model(client):
    # 传入模型 id 应锁定到该模型并回显相同 id
    r = client.post(
        "/v1/chat/completions",
        headers=GW_AUTH,
        json={"messages": [{"role": "user", "content": "hi"}], "model": "qwen-max", "stream": False},
    )
    assert r.status_code == 200
    assert r.json()["model"] == "qwen-max"
