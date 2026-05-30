"""JWT 工具：签发 / 校验 access token + refresh token。

access token TTL = settings.ACCESS_TOKEN_TTL (默认 1800s)
refresh token TTL = settings.REFRESH_TOKEN_TTL (默认 7d)
算法 HS256；secret 来自 settings.JWT_SECRET。
refresh token 使用 Redis 白名单机制，支持吊销。
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from jose import JWTError, jwt

from config import settings
from exceptions import BusinessException, ErrorCode

logger = logging.getLogger(__name__)

_ALG = settings.JWT_ALG
_SECRET = settings.JWT_SECRET.get_secret_value()

_REFRESH_KEY_PREFIX = "refresh:"


def _redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis as _redis_lib
        return _redis_lib.from_url(url, decode_responses=True)
    except Exception:
        return None


def _store_refresh_jti(user_id: int, jti: str, ttl: int) -> None:
    """将 refresh token jti 存入 Redis 白名单。"""
    r = _redis()
    if r is None:
        return
    try:
        key = f"{_REFRESH_KEY_PREFIX}{user_id}:{jti}"
        r.setex(key, ttl, 1)
    except Exception as exc:
        logger.warning("store_refresh_jti redis error: %s", exc)


def _verify_refresh_jti(user_id: int, jti: str) -> bool:
    """验证 refresh token jti 是否在 Redis 白名单中。"""
    r = _redis()
    if r is None:
        return True  # Redis 不可用时放行（开发降级）
    try:
        key = f"{_REFRESH_KEY_PREFIX}{user_id}:{jti}"
        return r.exists(key) > 0
    except Exception as exc:
        logger.warning("verify_refresh_jti redis error: %s", exc)
        return True


def _revoke_refresh_jti(user_id: int, jti: str) -> None:
    """从 Redis 白名单移除 refresh token jti。"""
    r = _redis()
    if r is None:
        return
    try:
        key = f"{_REFRESH_KEY_PREFIX}{user_id}:{jti}"
        r.delete(key)
    except Exception as exc:
        logger.warning("revoke_refresh_jti redis error: %s", exc)


def revoke_all_refresh_tokens(user_id: int) -> None:
    """吊销用户所有 refresh token（用于管理员强制登出）。"""
    r = _redis()
    if r is None:
        return
    try:
        pattern = f"{_REFRESH_KEY_PREFIX}{user_id}:*"
        for key in r.scan_iter(match=pattern, count=100):
            r.delete(key)
    except Exception as exc:
        logger.warning("revoke_all_refresh_tokens redis error: %s", exc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: int,
    tenant_id: int,
    roles: list[str],
    permissions: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    """签发 access token，携带 sub/tid/roles/perms/jti/type。"""
    now = _utcnow()
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "tid": tenant_id,
        "roles": roles,
        "perms": permissions,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=settings.ACCESS_TOKEN_TTL),
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, _SECRET, algorithm=_ALG)


def create_refresh_token(user_id: int, tenant_id: int) -> str:
    """签发 refresh token，只携带必要字段（type=refresh），jti 存入 Redis 白名单。"""
    now = _utcnow()
    jti = uuid.uuid4().hex
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "tid": tenant_id,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(seconds=settings.REFRESH_TOKEN_TTL),
    }
    token = jwt.encode(claims, _SECRET, algorithm=_ALG)
    _store_refresh_jti(user_id, jti, settings.REFRESH_TOKEN_TTL)
    return token


def verify_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """校验 token；失败统一抛 BusinessException(AUTH_TOKEN_INVALID / AUTH_TOKEN_EXPIRED)。

    refresh token 额外校验 Redis 白名单（已被吊销则拒绝）。
    """
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALG])
    except JWTError as exc:
        msg = str(exc)
        if "expired" in msg.lower():
            raise BusinessException(ErrorCode.AUTH_TOKEN_EXPIRED) from exc
        raise BusinessException(ErrorCode.AUTH_TOKEN_INVALID) from exc

    if payload.get("type") != expected_type:
        raise BusinessException(ErrorCode.AUTH_TOKEN_INVALID, message="token 类型不匹配")

    if expected_type == "refresh":
        user_id = int(payload["sub"])
        jti = payload.get("jti", "")
        if not _verify_refresh_jti(user_id, jti):
            raise BusinessException(ErrorCode.AUTH_TOKEN_INVALID, message="refresh token 已吊销")

    return payload


def revoke_refresh_token(user_id: int, token: str) -> None:
    """根据 refresh token 字符串吊销（提取 jti 后从 Redis 删除）。"""
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALG])
        jti = payload.get("jti", "")
        if jti:
            _revoke_refresh_jti(user_id, jti)
    except JWTError:
        pass


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "revoke_refresh_token",
    "revoke_all_refresh_tokens",
]
