"""执行器：把统一请求发给厂商。优先用 LiteLLM，未安装时走 Mock（便于本地全链路测试）。"""

import json
import logging
import os
import uuid
from typing import Any, AsyncIterator

from . import models
from .routing.capabilities import estimate_prompt_tokens

logger = logging.getLogger("llm_pool")

_LITELLM = None


def _load_litellm():
    global _LITELLM
    if _LITELLM is None:
        try:
            import litellm  # 延迟导入，避免启动时重依赖

            _LITELLM = litellm
        except Exception:
            _LITELLM = False
    return _LITELLM or None


def using_mock() -> bool:
    if os.getenv("LLM_POOL_FORCE_MOCK") == "1":
        return True
    return _load_litellm() is None


def _litellm_model_string(model_row: "models.Model", platform_row: "models.Platform | None" = None) -> str:
    """构造传给 LiteLLM 的 model 串。

    provider 以「平台级」为准：模型上的 provider 仅为可选覆盖，空则继承平台 provider。
    LiteLLM 对「非内置已知模型名」无法推断厂商，必须带 `provider/model` 前缀
    （如 `deepseek/deepseek-v4-flash-0731`）；OpenAI 兼容端点可用 `openai/<模型名>`。
    provider_model 若已含 '/' 前缀则不再重复拼接。
    """
    pm = model_row.provider_model or ""
    provider = getattr(model_row, "provider", None) or ""
    if not provider and platform_row is not None:
        provider = getattr(platform_row, "provider", None) or ""
    if provider and "/" not in pm:
        return f"{provider}/{pm}"
    return pm


async def complete(
    model_row: "models.Model",
    platform_row: "models.Platform",
    messages: list[dict],
    stream: bool,
    **kwargs: Any,
):
    """返回 OpenAI 兼容结构：非流式返回 dict；流式返回 chunk dict 的异步迭代器。"""
    litellm = _load_litellm()
    if os.getenv("LLM_POOL_FORCE_MOCK") == "1":
        litellm = None
    call_kwargs = {
        "model": _litellm_model_string(model_row, platform_row),
        "api_base": platform_row.api_base,
        "api_key": platform_row.api_key,
        "messages": messages,
        "stream": stream,
        **kwargs,
    }
    if litellm is not None:
        logger.info(
            "[CALL] litellm_model=%s platform=%s api_base=%s stream=%s",
            call_kwargs["model"],
            platform_row.id,
            platform_row.api_base,
            stream,
        )
        if stream:
            call_kwargs["stream_options"] = {"include_usage": True}
            resp = await litellm.acompletion(**call_kwargs)
            return _litellm_stream(resp)
        resp = await litellm.acompletion(**call_kwargs)
        return resp.model_dump()

    # ---- Mock 执行器 ----
    rid = "chatcmpl-" + uuid.uuid4().hex[:12]
    est_prompt = estimate_prompt_tokens(messages)
    content = (
        f"[MOCK] 平台={platform_row.name} 模型={model_row.name} "
        f"已收到 {len(messages)} 条消息（mock 模式，未真正调用厂商）。"
    )
    completion_tokens = max(1, len(content) // 3)
    usage = {
        "prompt_tokens": est_prompt,
        "completion_tokens": completion_tokens,
        "total_tokens": est_prompt + completion_tokens,
    }
    if stream:
        return _mock_stream(rid, model_row.id, content, usage)
    return {
        "id": rid,
        "object": "chat.completion",
        "created": __import__("time").time_ns() // 1_000_000_000,
        "model": model_row.id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


async def _litellm_stream(resp) -> AsyncIterator[dict]:
    async for chunk in resp:
        yield chunk.model_dump()


async def _mock_stream(rid: str, model_id: str, content: str, usage: dict) -> AsyncIterator[dict]:
    yield {
        "id": rid,
        "object": "chat.completion.chunk",
        "created": __import__("time").time_ns() // 1_000_000_000,
        "model": model_id,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    for i in range(0, len(content), 12):
        piece = content[i : i + 12]
        yield {
            "id": rid,
            "object": "chat.completion.chunk",
            "created": __import__("time").time_ns() // 1_000_000_000,
            "model": model_id,
            "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
        }
    yield {
        "id": rid,
        "object": "chat.completion.chunk",
        "created": __import__("time").time_ns() // 1_000_000_000,
        "model": model_id,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": usage,
    }
