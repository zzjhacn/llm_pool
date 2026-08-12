"""决策链：请求 → 能力解析 → 四层硬过滤 → 成本/质量打分 → 选中 / 降级。"""

from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models
from ..config import (
    DEFAULT_ROUTE_STRATEGY,
    ESCAPE_MODEL_ID,
    QUALITY_WEIGHT,
)
from ..ledger import book
from .capabilities import detect_capabilities, estimate_prompt_tokens

OUT_TOKENS_EST = 512  # 输出 token 估算，用于成本预估

# 结构化输出相关能力：请求携带 response_format / tools 时必须由模型声明支持，
# 否则在网关层即被排除（强一致场景不依赖上游强制，避免深层 400）。
STRUCTURED_CAPS = {"json_schema", "json_object", "function_calling"}


@dataclass
class RouteResult:
    model: "models.Model"
    package: Optional["models.ResourcePackage"]
    est_cost: float
    candidates: list[str] = field(default_factory=list)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    strategy: str = DEFAULT_ROUTE_STRATEGY
    escaped: bool = False


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
    messages: list[dict],
    pinned: Optional[str] = None,
    strategy: Optional[str] = None,
    response_format: Any = None,
    tools: Any = None,
) -> RouteResult:
    required = detect_capabilities(messages, response_format=response_format, tools=tools)
    est_prompt = estimate_prompt_tokens(messages)
    strategy = strategy or DEFAULT_ROUTE_STRATEGY

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
        if pinned and m.id != pinned and m.provider_model != pinned:
            reasons[m.id].append("not_pinned")
            continue
        est_cost = book.compute_cost(m, est_prompt, OUT_TOKENS_EST)
        candidates.append((m, est_cost))

    if pinned and not candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"指定模型 {pinned} 不可用（平台/能力/到期/额度不满足）；请求需要能力 {sorted(required)}",
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
                    est_cost=book.compute_cost(esc, est_prompt, OUT_TOKENS_EST),
                    candidates=[],
                    reasons=reasons,
                    strategy=strategy,
                    escaped=True,
                )
        # 结构化输出能力缺口：请求明确需要某结构化模式，但池中无可用模型支持。
        # 早失败并返回清晰提示，避免把请求转发到不支持的模型而得到深层 400。
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
    )
