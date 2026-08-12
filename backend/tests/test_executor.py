"""执行器：发给 LiteLLM 的 model 串必须带 provider 前缀。"""
from app.executor import _litellm_model_string


class _FakeModel:
    def __init__(self, provider_model, provider=None):
        self.provider_model = provider_model
        self.provider = provider


class _FakePlatform:
    def __init__(self, provider="openai"):
        self.provider = provider


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
