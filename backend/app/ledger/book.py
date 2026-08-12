import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger("llm_pool")


def compute_cost(model: "models.Model", prompt_tokens: int, completion_tokens: int) -> float:
    """按有效计费方式计算本次成本（货币）。计费方式跟随额度来源。"""
    if model.effective_billing_type == "call":
        return float(model.price_per_call)
    return (prompt_tokens / 1000.0) * float(model.price_input) + (
        completion_tokens / 1000.0
    ) * float(model.price_output)


def units_for(model: "models.Model", prompt_tokens: int, completion_tokens: int) -> float:
    """按有效计费方式计算本次扣减的资源量。"""
    if model.effective_billing_type == "call":
        return 1.0
    return float(prompt_tokens + completion_tokens)


def sync_model_states(session: Session) -> None:
    """重算所有模型的 enabled：过期 / 额度耗尽自动置否；手动关闭优先级最高。

    额度来源两种：
    - 共享包：包耗尽则级联禁用该包下所有模型。
    - 模型独立额度：自身额度耗尽仅禁用自己。
    恢复规则：未过期、额度未耗尽、且非手动关闭 → 自动启用。
    """
    now = datetime.now(timezone.utc)
    for m in session.query(models.Model).all():
        if m.manual_disabled:
            m.enabled = False
            continue
        if m.is_expired:
            m.enabled = False
            continue
        if m.has_quota and m.quota_balance_eff <= 0:
            m.enabled = False
            continue
        m.enabled = True
    session.commit()


def record_usage(
    session: Session,
    *,
    model: "models.Model",
    request_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    client_key: str | None,
    route_strategy: str | None,
) -> "models.UsageLog":
    """原子扣减额度并写日志。失败（异常）由调用方回滚。

    扣减按额度来源分叉：
    - 共享包：扣 package.used，耗尽则级联熔断同包全部模型。
    - 模型独立额度：扣 model.quota_used，耗尽则仅停用自己。
    - 无额度（兜底）：不扣减。
    """
    units = units_for(model, prompt_tokens, completion_tokens)
    cost = compute_cost(model, prompt_tokens, completion_tokens)
    source = model.quota_source

    if source == "package":
        model.package.used += units
    elif source == "self":
        model.quota_used += units

    log = models.UsageLog(
        request_id=request_id,
        client_key=client_key,
        model_id=model.id,
        platform_id=model.platform_id,
        package_id=model.package_id,
        billing_type=model.effective_billing_type,
        units=units,
        cost=cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        route_strategy=route_strategy,
        quota_source=source,
    )
    session.add(log)
    session.flush()

    if source == "package" and model.package is not None and model.package.exhausted:
        for sibling in session.query(models.Model).filter_by(package_id=model.package_id).all():
            if not sibling.manual_disabled:
                sibling.enabled = False
                logger.info("额度包 %s 耗尽，自动熔断模型 %s", model.package_id, sibling.id)
    elif source == "self" and model.quota_balance_eff <= 0:
        if not model.manual_disabled:
            model.enabled = False
            logger.info("模型 %s 独立额度耗尽，自动停用", model.id)

    session.commit()
    return log
