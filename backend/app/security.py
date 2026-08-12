import base64
import binascii
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .config import ADMIN_PASSWORD, ADMIN_USERNAME, GATEWAY_API_KEYS, SECRET

# 管理面：Authorization: Bearer <admin_token>
_admin_scheme = HTTPBearer(auto_error=False)
# 业务面：Authorization: Bearer <gateway_key> 或 api-key 头
_gateway_scheme = APIKeyHeader(name="api-key", auto_error=False)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _hmac(payload: str) -> str:
    return _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())


def create_admin_token(username: str) -> str:
    payload = _b64(username.encode())
    sig = _hmac(payload)
    return f"{payload}.{sig}"


def verify_admin_token(token: Optional[str]) -> Optional[str]:
    if not token or "." not in token:
        return None
    payload, sig = token.split(".", 1)
    if not hmac.compare_digest(_hmac(payload), sig):
        return None
    try:
        return _b64d(payload).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None


def authenticate_admin(username: str, password: str) -> bool:
    # 常量时间比较，避免用户名枚举/时序攻击
    u_ok = hmac.compare_digest(username, ADMIN_USERNAME)
    p_ok = hmac.compare_digest(password, ADMIN_PASSWORD)
    return u_ok and p_ok


async def require_admin(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_admin_scheme),
) -> str:
    username = verify_admin_token(cred.credentials if cred else None)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或缺失管理 token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


def _resolve_gateway_key(
    cred: Optional[HTTPAuthorizationCredentials],
    api_key: Optional[str],
) -> Optional[str]:
    if cred and cred.credentials:
        return cred.credentials
    return api_key


async def require_gateway_key(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_admin_scheme),
    api_key: Optional[str] = Depends(_gateway_scheme),
) -> str:
    key = _resolve_gateway_key(cred, api_key)
    if not key or key not in GATEWAY_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或缺失网关 key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return key
