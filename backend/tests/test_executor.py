"""执行器：发给 LiteLLM 的 model 串必须带 provider 前缀。"""
from app.executor import _litellm_model_string


class _FakeModel:
    def __init__(self, provider_model, provider=None, id=None):
        self.provider_model = provider_model
        self.provider = provider
        self.id = id or provider_model


class _FakePlatform:
    def __init__(self, provider="openai", api_base="https://api.example.com/v1", api_key="sk-test"):
        self.provider = provider
        self.api_base = api_base
        self.api_key = api_key


def test_prefix_added_when_provider_set():
    m = _FakeModel(provider_model="deepseek-v4-flash-0731", provider="deepseek")
    assert _litellm_model_string(m) == "deepseek/deepseek-v4-flash-0731"


def test_no_double_prefix_when_already_prefixed():
    m = _FakeModel(provider_model="deepseek/deepseek-chat", provider="deepseek")
    assert _litellm_model_string(m) == "deepseek/deepseek-chat"


def test_no_prefix_when_provider_empty():
    m = _FakeModel(provider_model="gpt-4o", provider="")
    assert _litellm_model_string(m) == "gpt-4o"


def test_openai_compatible_prefix():
    m = _FakeModel(provider_model="qwen-max", provider="openai")
    assert _litellm_model_string(m) == "openai/qwen-max"


def test_provider_inherited_from_platform_when_model_override_empty():
    # provider 是平台级属性：模型未覆盖时继承平台
    m = _FakeModel(provider_model="deepseek-v4-flash-0731", provider=None)
    plat = _FakePlatform(provider="openai")
    assert _litellm_model_string(m, plat) == "openai/deepseek-v4-flash-0731"


def test_model_provider_override_takes_precedence():
    # 极少数场景：模型显式覆盖平台 provider
    m = _FakeModel(provider_model="deepseek-v4-flash-0731", provider="deepseek")
    plat = _FakePlatform(provider="openai")
    assert _litellm_model_string(m, plat) == "deepseek/deepseek-v4-flash-0731"


# ---------------- embed() 单元测试（FORCE_MOCK 走 mock 分支） ----------------
def test_embed_mock_single_string_returns_openai_shape(monkeypatch):
    import asyncio
    from app.executor import embed

    monkeypatch.setenv("LLM_POOL_FORCE_MOCK", "1")
    m = _FakeModel(provider_model="text-embedding-3-small", provider="openai", id="text-embedding-3-small")
    plat = _FakePlatform(provider="openai")
    out = asyncio.run(embed(m, plat, "你好世界"))
    assert out["object"] == "list"
    assert isinstance(out["data"], list) and len(out["data"]) == 1
    emb = out["data"][0]
    assert emb["object"] == "embedding"
    assert emb["index"] == 0
    assert isinstance(emb["embedding"], list) and len(emb["embedding"]) == 8
    assert out["usage"]["prompt_tokens"] == 2
    assert out["model"] == "text-embedding-3-small"


def test_embed_mock_batch_list_returns_multiple(monkeypatch):
    import asyncio
    from app.executor import embed

    monkeypatch.setenv("LLM_POOL_FORCE_MOCK", "1")
    m = _FakeModel(provider_model="text-embedding-3-small", provider="openai", id="text-embedding-3-small")
    plat = _FakePlatform(provider="openai")
    out = asyncio.run(embed(m, plat, ["a", "b", "c"]))
    assert len(out["data"]) == 3
    assert [d["index"] for d in out["data"]] == [0, 1, 2]
    assert out["usage"]["prompt_tokens"] == 6  # 3 条 × 2 mock token

