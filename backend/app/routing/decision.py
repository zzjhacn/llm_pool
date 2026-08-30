"""决策链：请求 → 能力解析 → 四层硬过滤 → 成本/质量打分 → 选中 / 降级。"""

import logging
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..config import (
    DEFAULT_ROUTE_STRATEGY,
    ESCAPE_MODEL_ID,
    QUALITY_WEIGHT,
)
from ..ledger import book
from .capabilities import detect_capabilities, estimate_prompt_tokens

logger = logging.getLogger("llm_pool")

OUT_TOKENS_EST = 512  # 输出 token 估算，用于成本预估

# 结构化输出相关能力：请求携带 response_format / tools 时必须由模型声明支持，
# 否则在网关层即被排除（强一致场景不依赖上游强制，避免深层 400）。
STRUCTURED_CAPS = {"json_schema", "json_object", "function_calling"}

# 指定模型被「按未传处理」（回退自动选择）的原因文案
PIN_DROP_REASONS = {
    "not_found": "模型中不存在该名称",
    "expired": "模型已过期",
    "quota_exhausted": "模型额度已耗尽",
    "unavailable": "模型不可用",
}


@dataclass
class RouteResult:
    model: "models.Model"
    package: Optional["models.ResourcePackage"]
    est_cost: float
    candidates: list[str] = field(default_factory=list)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    strategy: str = DEFAULT_ROUTE_STRATEGY
    escaped: bool = False
    # 客户端请求时指定的模型名（pinned），以及它是否因不可用而被降级为「未传」
    pin_requested: Optional[str] = None
    pin_dropped: Optional[str] = None


def _resolve_pin(session: Session, pinned: str) -> tuple[Optional[str], Optional[str]]:
    """判定客户端指定的模型名是否继续生效。

    返回 (生效的 pinned, 丢弃原因)；丢弃原因非 None 时表示该模型「按未传处理」，
    请求进入自动选择逻辑，不再因它报 400。

    仅以下三种情况降级为自动选择：
      - not_found：池中不存在该名称（既不匹配 Model.id 也不匹配 provider_model）
      - expired：存在但已过期
      - quota_exhausted：存在但额度耗尽

    其余不可用原因（平台/模型被停用、能力不匹配等）属于显式配置或强一致约束，
    不自动降级，仍走原来的 400 早失败，避免悄悄把请求转到不相干的模型上。
    """
    matches = (
        session.query(models.Model)
        .filter(or_(models.Model.id == pinned, models.Model.provider_model == pinned))
        .all()
    )
    if not matches:
        return None, "not_found"

    # 同名可能命中多个平台上的模型：只要有一个可用就继续锁定
    drop_reasons: set[str] = set()
    for m in matches:
        if m.is_expired:
            drop_reasons.add("expired")
        elif m.quota_exhausted:
            drop_reasons.add("quota_exhausted")
        else:
            return pinned, None

    if drop_reasons == {"expired"}:
        return None, "expired"
    if drop_reasons == {"quota_exhausted"}:
        return None, "quota_exhausted"
    return None, "unavailable"


def _score(candidates: list[tuple["models.Model", float]], strategy: str):
    """返回按策略排序后的候选（score 高者优先）。candidates: [(model, est_cost)]。"""
    if strategy == "lowest_cost":
        return sorted(candidates, key=lambda c: c[1])
    if strategy == "highest_quality":
        return sorted(candidates, key=lambda c: (-c[0].quality_tier, -_balance(c[0])))
    if strategy == "lowest_latency":
        return sorted(candidates, key=lambda c: (c[0].latency_tier, -c[0].quality_tier))
    if strategy == "expiring_soon":
        return sorted(candidates, key=lambda c: (_expiry_key(c[0]), -_balance(c[0])))
    # balanced（默认）
    costs = [c[1] for c in candidates] or [1.0]
    max_cost = max(costs) or 1.0
    max_q = max((c[0].quality_tier for c in candidates), default=5) or 5

    def balanced_score(c):
        norm_cost = c[1] / max_cost
        norm_q = c[0].quality_tier / max_q
        return QUALITY_WEIGHT * norm_q - (1 - QUALITY_WEIGHT) * norm_cost

    return sorted(candidates, key=lambda c: (-balanced_score(c), -_balance(c[0])))


def _balance(m: "models.Model") -> float:
    if m.package is not None:
        return m.package.balance
    if m.quota_source == "self":
        return m.quota_balance_eff
    return float("inf")


def _expiry_key(m: "models.Model") -> float:
    """快到期优先：返回到期时间戳；未设置到期则视为最远（最不优先）。"""
    if m.expired_at is None:
        return float("inf")
    exp = m.expired_at
    if exp.tzinfo is None:  # SQLite 读回为 naive，按 UTC 处理
        exp = exp.replace(tzinfo=timezone.utc)
    return exp.timestamp()


def route(
    session: Session,
    messages: list[dict] | None = None,
    pinned: Optional[str] = None,
    strategy: Optional[str] = None,
    response_format: Any = None,
    tools: Any = None,
    kind: str = "chat",
) -> RouteResult:
    """按请求类型路由。

    - kind="chat"（默认）：从 messages + response_format/tools 解析所需能力。
    - kind="embedding"：所需能力恒为 {"embedding"}，不看 messages。
    """
    if kind == "embedding":
        required: set[str] = {"embedding"}
        est_prompt = 0
    else:
        required = detect_capabilities(messages or [], response_format=response_format, tools=tools)
        est_prompt = estimate_prompt_tokens(messages or [])
    strategy = strategy or DEFAULT_ROUTE_STRATEGY
    # embedding 没有输出 token，成本仅按输入估算
    est_completion = 0 if kind == "embedding" else OUT_TOKENS_EST

    # 指定模型不可用（不存在 / 已过期 / 额度耗尽）时按「未传」处理，进入自动选择
    pin_effective: Optional[str] = pinned
    pin_dropped: Optional[str] = None
    if pinned:
        pin_effective, pin_dropped = _resolve_pin(session, pinned)
        if pin_dropped:
            logger.warning(
                "[ROUTE] pinned=%s 不可用（%s），按未传处理，进入自动选择",
                pinned,
                PIN_DROP_REASONS.get(pin_dropped, pin_dropped),
            )

    reasons: dict[str, list[str]] = {}
    candidates: list[tuple[models.Model, float]] = []

    for m in session.query(models.Model).all():
        reasons.setdefault(m.id, [])
        plat = m.platform
        if not plat or not plat.enabled:
            reasons[m.id].append("platform_disabled")
            continue
        if not m.enabled or m.manual_disabled:
            reasons[m.id].append("model_disabled")
            continue
        if m.is_expired:
            reasons[m.id].append("expired")
            continue
        missing = [c for c in required if c not in (m.capabilities or [])]
        if missing:
            reasons[m.id].append(f"cap_missing:{missing}")
            continue
        if m.has_quota and m.quota_balance_eff <= 0:
            reasons[m.id].append("quota_exhausted")
            continue
        if pin_effective and m.id != pin_effective and m.provider_model != pin_effective:
            reasons[m.id].append("not_pinned")
            continue
        est_cost = book.compute_cost(m, est_prompt, est_completion)
        candidates.append((m, est_cost))

    if pin_effective and not candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"指定模型 {pin_effective} 不可用（平台/模型被停用或能力不满足）；请求需要能力 {sorted(required)}",
        )

    if not candidates:
        if ESCAPE_MODEL_ID:
            esc = session.get(models.Model, ESCAPE_MODEL_ID)
            if (
                esc
                and esc.enabled
                and not esc.manual_disabled
                and (not esc.has_quota or esc.quota_balance_eff > 0)
                and required.issubset(set(esc.capabilities or []))
            ):
                return RouteResult(
                    model=esc,
                    package=esc.package,
                    est_cost=book.compute_cost(esc, est_prompt, est_completion),
                    candidates=[],
                    reasons=reasons,
                    strategy=strategy,
                    escaped=True,
                    pin_requested=pinned,
                    pin_dropped=pin_dropped,
                )
        # 结构化输出能力缺口：请求明确需要某结构化模式，但池中无可用模型支持。
        # 早失败并返回清晰提示，避免把请求转发到不支持的模型而得到深层 400。
        if kind == "embedding":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "无可用模型：请求需要 embedding 能力，但当前模型池中"
                    "没有匹配的可用模型。请为支持 embeddings 的模型打上 embedding 能力标签。"
                ),
            )
        required_structured = required & STRUCTURED_CAPS
        if required_structured:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"无可用模型：请求需要结构化输出能力 {sorted(required_structured)}，"
                    f"但当前模型池中没有匹配的可用模型。"
                    f"请为支持该模式的模型打上相应能力标签"
                    f"（json_schema / json_object / function_calling），"
                    f"或在强一致场景改用支持 json_schema 的模型。"
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="无可用模型（候选为空）",
        )

    ranked = _score(candidates, strategy)
    best, best_cost = ranked[0]
    return RouteResult(
        model=best,
        package=best.package,
        est_cost=best_cost,
        candidates=[c[0].id for c in ranked],
        reasons=reasons,
        strategy=strategy,
        pin_requested=pinned,
        pin_dropped=pin_dropped,
    )
