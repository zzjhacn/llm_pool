from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from typing import Optional

from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from .db import Base


class _JSONList(TypeDecorator):
    """把 Python list 存成 JSON 字符串，读取时还原。"""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        import json

        return json.dumps(value or []) if value is not None else "[]"

    def process_result_value(self, value, dialect):
        import json

        if not value:
            return []
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []


def _now():
    return datetime.now(timezone.utc)


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(String, primary_key=True)  # slug，如 "aliyun"
    name = Column(String, nullable=False)
    api_base = Column(String, nullable=False)
    api_key = Column(String, nullable=False)  # v1 明文存储，生产应加密/KMS
    # provider 是「平台级」属性：由平台端点形态决定（OpenAI 兼容端点→openai；
    # 厂商原生端点→dashscope/azure/...）。模型默认继承平台 provider，少数情况可在模型上覆盖。
    provider = Column(String, nullable=True, default="openai")
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    models = relationship("Model", back_populates="platform", cascade="all, delete-orphan")


class ResourcePackage(Base):
    __tablename__ = "resource_packages"

    id = Column(String, primary_key=True)  # slug
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="token")  # token | call
    capacity = Column(Float, default=0.0, nullable=False)  # 总资源量
    used = Column(Float, default=0.0, nullable=False)  # 已用资源量（单调递增）
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    @property
    def balance(self) -> float:
        return max(0.0, self.capacity - self.used)

    @property
    def exhausted(self) -> bool:
        return self.balance <= 0


class Model(Base):
    __tablename__ = "models"

    id = Column(String, primary_key=True)  # slug，如 "qwen-max"；同时也是客户端调用时使用的 model 名
    platform_id = Column(String, ForeignKey("platforms.id"), nullable=False)
    name = Column(String, nullable=False)  # 展示名
    # provider 现在归平台所有；模型上的 provider 仅作为「可选覆盖」：为空时继承平台 provider。
    provider = Column(String, nullable=True)  # LiteLLM 厂商键覆盖（可选）；空=继承平台
    provider_model = Column(String, nullable=False)  # 实际发给厂商的模型串
    capabilities = Column(_JSONList, default=[], nullable=False)  # 能力标签集合
    billing_type = Column(String, default="token", nullable=False)  # token | call
    price_input = Column(Float, default=0.0, nullable=False)  # 每 1K token 输入价（token 计费）
    price_output = Column(Float, default=0.0, nullable=False)  # 每 1K token 输出价
    price_per_call = Column(Float, default=0.0, nullable=False)  # 每次调用价（call 计费）
    quality_tier = Column(Integer, default=2, nullable=False)  # 1~5，越高越好
    latency_tier = Column(Integer, default=3, nullable=False)  # 1~5，越低越快
    context_window = Column(Integer, default=0, nullable=False)  # 上下文上限 token
    expired_at = Column(DateTime, nullable=True)  # 到期（仅模型层，见设计决策①）
    package_id = Column(String, ForeignKey("resource_packages.id"), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)  # 最终生效开关
    manual_disabled = Column(Boolean, default=False, nullable=False)  # 手动关闭优先级最高
    quota_capacity = Column(Float, nullable=True, default=None)  # 模型独立额度总量（无共享包时生效）
    quota_used = Column(Float, default=0.0, nullable=False)  # 模型独立额度已用（单调递增）
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    platform = relationship("Platform", back_populates="models")
    package = relationship("ResourcePackage")

    @property
    def is_expired(self) -> bool:
        if self.expired_at is None:
            return False
        exp = self.expired_at
        if exp.tzinfo is None:  # SQLite 不保留时区，读回为 naive，按 UTC 处理
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= datetime.now(timezone.utc)

    # ---- 额度来源抽象：共享包 / 模型独立额度 / 无额度（兜底） ----
    @property
    def quota_source(self) -> str:
        """额度来源：package=共享额度包；self=模型独立额度；none=无额度（兜底/无限）。"""
        if self.package_id:
            return "package"
        if self.quota_capacity is not None:
            return "self"
        return "none"

    @property
    def effective_billing_type(self) -> str:
        """计费方式跟随额度来源：共享包取包的 unit，独立额度取自身 billing_type。"""
        if self.package_id and self.package is not None:
            return self.package.unit
        return self.billing_type

    @property
    def quota_capacity_eff(self) -> Optional[float]:
        if self.package_id and self.package is not None:
            return self.package.capacity
        return self.quota_capacity

    @property
    def quota_used_eff(self) -> float:
        if self.package_id and self.package is not None:
            return self.package.used
        return self.quota_used or 0.0

    @property
    def quota_balance_eff(self) -> Optional[float]:
        if self.quota_source == "none":
            return None
        return max(0.0, (self.quota_capacity_eff or 0.0) - self.quota_used_eff)

    @property
    def has_quota(self) -> bool:
        return self.quota_source != "none"

    @property
    def quota_exhausted(self) -> bool:
        return self.has_quota and (self.quota_balance_eff or 0.0) <= 0.0


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, nullable=False, index=True)
    client_key = Column(String, nullable=True)  # 网关 key 尾号/标识
    model_id = Column(String, nullable=False)
    platform_id = Column(String, nullable=False)
    package_id = Column(String, nullable=True)
    billing_type = Column(String, nullable=False)
    units = Column(Float, default=0.0, nullable=False)  # 扣减的资源量（token 数或 1 次）
    cost = Column(Float, default=0.0, nullable=False)  # 估算成本（货币）
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    route_strategy = Column(String, nullable=True)
    quota_source = Column(String, nullable=True)  # package | self | none（记录本次扣减来源）
    created_at = Column(DateTime, default=_now, nullable=False)
