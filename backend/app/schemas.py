from datetime import date, datetime, timezone
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field


def parse_dt(v: Union[None, str, date, datetime]) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, date):
        dt = datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    else:
        s = str(v).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------- Platform ----------------
class PlatformCreate(BaseModel):
    id: str
    name: str
    api_base: str
    api_key: str
    provider: str = "openai"  # 平台级 LiteLLM 厂商键（OpenAI 兼容端点用 openai）
    enabled: bool = True


class PlatformUpdate(BaseModel):
    name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    provider: Optional[str] = None
    enabled: Optional[bool] = None


class PlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    api_base: str
    api_key: str
    provider: str = "openai"
    enabled: bool


# ---------------- ResourcePackage ----------------
class PackageCreate(BaseModel):
    id: str
    name: str
    unit: str = Field("token", pattern="^(token|call)$")
    capacity: float
    used: float = 0.0


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = Field(None, pattern="^(token|call)$")
    capacity: Optional[float] = None
    used: Optional[float] = None


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    unit: str
    capacity: float
    used: float
    balance: float


# ---------------- Model ----------------
class ModelCreate(BaseModel):
    id: str
    platform_id: str
    name: str
    provider: Optional[str] = None  # 可选覆盖：为空则继承平台 provider
    provider_model: str
    capabilities: list[str] = []
    billing_type: str = Field("token", pattern="^(token|call)$")
    price_input: float = 0.0
    price_output: float = 0.0
    price_per_call: float = 0.0
    quality_tier: int = 2
    latency_tier: int = 3
    context_window: int = 0
    expired_at: Optional[str] = None
    package_id: Optional[str] = None
    quota_capacity: Optional[float] = None  # 模型独立额度总量（与 package_id 互斥）
    quota_used: Optional[float] = None
    enabled: bool = True
    manual_disabled: bool = False


class ModelUpdate(BaseModel):
    platform_id: Optional[str] = None
    name: Optional[str] = None
    provider: Optional[str] = None
    provider_model: Optional[str] = None
    capabilities: Optional[list[str]] = None
    billing_type: Optional[str] = Field(None, pattern="^(token|call)$")
    price_input: Optional[float] = None
    price_output: Optional[float] = None
    price_per_call: Optional[float] = None
    quality_tier: Optional[int] = None
    latency_tier: Optional[int] = None
    context_window: Optional[int] = None
    expired_at: Optional[str] = None
    package_id: Optional[str] = None
    quota_capacity: Optional[float] = None
    quota_used: Optional[float] = None
    enabled: Optional[bool] = None
    manual_disabled: Optional[bool] = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    platform_id: str
    name: str
    provider: Optional[str] = None  # 可选覆盖（继承平台则为 None）
    effective_provider: Optional[str] = None  # 实际生效的 provider（模型覆盖或继承平台）
    provider_model: str
    capabilities: list[str]
    billing_type: str
    price_input: float
    price_output: float
    price_per_call: float
    quality_tier: int
    latency_tier: int
    context_window: int
    expired_at: Optional[datetime]
    package_id: Optional[str]
    package_balance: Optional[float] = None
    quota_source: str
    quota_capacity: Optional[float] = None
    quota_used: float = 0.0
    quota_balance: Optional[float] = None
    enabled: bool
    manual_disabled: bool


# ---------------- Admin login / ledger ----------------
class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    username: str


class LedgerSummary(BaseModel):
    total_cost: float
    total_calls: int
    total_units: float
    by_model: list[dict]
    recent: list[dict]
