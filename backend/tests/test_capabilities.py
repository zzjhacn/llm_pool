"""能力解析：消息文本 + response_format/tools 结构化输出能力。"""
from app.routing.capabilities import detect_capabilities


def test_chat_only_has_no_structured_cap():
    caps = detect_capabilities([{"role": "user", "content": "你好"}])
    assert "chat" in caps
    assert not (caps & {"json_schema", "json_object", "function_calling"})


def test_json_schema_request_detects_cap():
    caps = detect_capabilities(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_schema", "json_schema": {"name": "X"}},
    )
    assert "json_schema" in caps


def test_json_object_request_detects_cap():
    caps = detect_capabilities(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )
    assert "json_object" in caps


def test_tools_request_detects_function_calling():
    caps = detect_capabilities(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
    )
    assert "function_calling" in caps


def test_text_function_mention_still_adds_function_calling():
    caps = detect_capabilities([{"role": "user", "content": "请调用工具完成"}])
    assert "function_calling" in caps
