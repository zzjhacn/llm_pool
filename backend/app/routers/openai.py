import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request

logger = logging.getLogger("llm_pool")
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..executor import complete
from ..ledger import book
from ..routing import capabilities
from ..routing.decision import route
from ..security import require_gateway_key

router = APIRouter(tags=["openai"])


class ChatMessage(BaseModel):
    role: str
    content: object


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    route_strategy: str | None = None
    model_config = ConfigDict(extra="allow")


def _to_dict_messages(messages: list[ChatMessage]) -> list[dict]:
    out = []
    for m in messages:
        content = m.content
        out.append({"role": m.role, "content": content if isinstance(content, (str, list)) else json.dumps(content, ensure_ascii=False)})
    return out


@router.get("/v1/models")
def list_models(_: str = Depends(require_gateway_key), db: Session = Depends(get_db)):
    """列出当前可用模型（平台启用 + 模型启用 + 未过期 + 额度充足）。"""
    out = []
    for m in db.query(models.Model).all():
        if not m.platform.enabled or not m.enabled or m.manual_disabled:
            continue
        if m.is_expired:
            continue
        if m.package is not None and m.package.exhausted:
            continue
        out.append(
            {
                "id": m.id,
                "object": "model",
                "platform": m.platform_id,
                "capabilities": m.capabilities,
                "billing_type": m.billing_type,
                "quality_tier": m.quality_tier,
            }
        )
    return {"object": "list", "data": out}


@router.post("/v1/chat/completions")
async def chat_completions(
    req: ChatRequest,
    request: Request,
    client_key: str = Depends(require_gateway_key),
    db: Session = Depends(get_db),
):
    messages = _to_dict_messages(req.messages)
    result = route(
        db,
        messages,
        # model 不传或为空串 "" 时视为「自动选择」（由决策链按能力/余额/成本挑选）；
        # 传入具体值则锁定到该模型。可传模型 ID 或 provider_model 串（二者等价）。
        pinned=req.model or None,
        strategy=req.route_strategy,
    )

    # 透传给执行器的额外参数（temperature / max_tokens 等）
    extra = {k: v for k, v in req.model_extra.items()} if req.model_extra else {}
    if req.temperature is not None:
        extra["temperature"] = req.temperature
    if req.max_tokens is not None:
        extra["max_tokens"] = req.max_tokens

    rid = "req-" + uuid.uuid4().hex[:16]

    # 记录本次路由结果（每次调用必打）：选中模型、是否降级兜底、候选列表
    logger.info(
        "[ROUTE] request_id=%s pinned=%s -> model_id=%s platform=%s provider=%s provider_model=%s escaped=%s strategy=%s candidates=%s",
        rid,
        req.model or None,
        result.model.id,
        result.model.platform_id,
        getattr(result.model, "provider", "") or "",
        result.model.provider_model,
        result.escaped,
        result.strategy,
        result.candidates,
    )

    if not req.stream:
        data = await complete(result.model, result.model.platform, messages, stream=False, **extra)
        data["model"] = result.model.id
        usage = data.get("usage") or {}
        _deduct(db, result, usage, rid, client_key)
        return data

    # ---- 流式 ----
    async def event_stream():
        content_parts: list[str] = []
        usage_captured: dict = {}
        async for chunk in await complete(result.model, result.model.platform, messages, stream=True, **extra):
            chunk["model"] = result.model.id
            if chunk.get("usage"):
                usage_captured = chunk["usage"]
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            if isinstance(delta.get("content"), str):
                content_parts.append(delta["content"])
            yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"

        if usage_captured:
            usage = usage_captured
        else:
            prompt_t = capabilities.estimate_prompt_tokens(messages)
            comp_t = max(1, len("".join(content_parts)) // 3)
            usage = {"prompt_tokens": prompt_t, "completion_tokens": comp_t, "total_tokens": prompt_t + comp_t}
        _deduct(db, result, usage, rid, client_key)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _deduct(db: Session, result, usage: dict, rid: str, client_key: str) -> None:
    try:
        book.record_usage(
            db,
            model=result.model,
            request_id=rid,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            client_key=client_key[:8] if client_key else None,
            route_strategy=result.strategy,
        )
    except Exception as e:  # 扣减失败不影响已返回/已流式的内容，仅记录
        logger.exception("[ledger] 扣减失败 request=%s", rid)
