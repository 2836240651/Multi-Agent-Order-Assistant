"""用户服务：查询用户、bcrypt 密码校验、5 次失败锁定（Redis 计数器）。

锁定策略：Redis key = login_fail:{tenant_id}:{user_id}，TTL = 5min，
          连续失败 ≥ 5 次锁定；解锁通过 unlock_user() 或等 TTL 自然过期。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

from exceptions import BusinessException, ErrorCode

logger = logging.getLogger(__name__)

_LOCK_TTL_SECONDS = 300  # 5min
_MAX_FAILURES = 5
_FAIL_KEY_PREFIX = "login_fail:"


def _redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis as _redis_lib
        return _redis_lib.from_url(url, decode_responses=True)
    except Exception:
        return None


def _fail_key(tenant_id: int, user_id: int) -> str:
    return f"{_FAIL_KEY_PREFIX}{tenant_id}:{user_id}"


def record_login_failure(tenant_id: int, user_id: int) -> int:
    """记录一次登录失败；返回当前累计失败次数。"""
    r = _redis()
    if r is None:
        return 0
    key = _fail_key(tenant_id, user_id)
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, _LOCK_TTL_SECONDS)
        return int(count)
    except Exception as exc:
        logger.warning("record_login_failure redis error: %s", exc)
        return 0


def clear_login_failures(tenant_id: int, user_id: int) -> None:
    """登录成功后清除失败计数。"""
    r = _redis()
    if r is None:
        return
    try:
        r.delete(_fail_key(tenant_id, user_id))
    except Exception as exc:
        logger.warning("clear_login_failures redis error: %s", exc)


def is_locked(tenant_id: int, user_id: int) -> bool:
    """检查用户是否因失败次数过多被锁定。"""
    r = _redis()
    if r is None:
        return False
    try:
        val = r.get(_fail_key(tenant_id, user_id))
        return val is not None and int(val) >= _MAX_FAILURES
    except Exception as exc:
        logger.warning("is_locked redis error: %s", exc)
        return False


def unlock_user(tenant_id: int, user_id: int) -> None:
    """管理员手动解锁。"""
    clear_login_failures(tenant_id, user_id)


def verify_password(plain: str, hashed: str) -> bool:
    """bcrypt 密码比对；失败返回 False 而不是抛异常。"""
    try:
        import bcrypt
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def hash_password(plain: str) -> str:
    """生成 bcrypt hash（salt rounds=12）。"""
    import bcrypt
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(12)).decode()


async def authenticate_user(
    username: str,
    password: str,
    tenant_id: int,
) -> "dict":
    """查用户 → 校验密码 → 检查锁定；成功返回用户 dict，失败抛 BusinessException。"""
    from db.session import async_session
    from db.models import User
    from db.tenant_context import set_current_tenant
    from sqlalchemy import select

    set_current_tenant(tenant_id)

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == username, User.tenant_id == tenant_id)
        )
        user = result.scalar_one_or_none()

    if user is None:
        raise BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS)

    if is_locked(tenant_id, user.id):
        raise BusinessException(ErrorCode.AUTH_USER_LOCKED)

    if not verify_password(password, user.password_hash):
        count = record_login_failure(tenant_id, user.id)
        if count >= _MAX_FAILURES:
            raise BusinessException(ErrorCode.AUTH_USER_LOCKED)
        raise BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS)

    if user.status != 1:
        raise BusinessException(ErrorCode.AUTH_USER_LOCKED)

    clear_login_failures(tenant_id, user.id)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "tenant_id": user.tenant_id,
        "email": user.email,
    }


async def get_user_roles_and_perms(user_id: int, tenant_id: int) -> tuple[list[str], list[str]]:
    """查询用户拥有的角色列表和权限列表（用于 token claims）。

    Redis 缓存：key = perms:{tenant_id}:{user_id}，TTL = 60s。
    """
    import json as _json

    cache_key = f"perms:{tenant_id}:{user_id}"
    r = _redis()

    # 读缓存
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                data = _json.loads(cached)
                return data["roles"], data["perms"]
        except Exception:
            pass

    from db.session import async_session
    from db.models import UserRole, Role
    from db.tenant_context import set_current_tenant
    from sqlalchemy import select

    set_current_tenant(tenant_id)

    roles: list[str] = []
    perms: list[str] = []

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id, UserRole.tenant_id == tenant_id)
            )
            role_objs = result.scalars().all()
            for rv in role_objs:
                roles.append(rv.name)
                for p in rv.permissions:
                    perms.append(p.code)
    except Exception as exc:
        logger.warning("get_user_roles_and_perms failed: %s", exc)

    unique_perms = list(set(perms))

    # 写缓存
    if r:
        try:
            r.set(cache_key, _json.dumps({"roles": roles, "perms": unique_perms}), ex=60)
        except Exception:
            pass

    return roles, unique_perms


__all__ = [
    "authenticate_user",
    "get_user_roles_and_perms",
    "verify_password",
    "hash_password",
    "record_login_failure",
    "clear_login_failures",
    "is_locked",
    "unlock_user",
]
