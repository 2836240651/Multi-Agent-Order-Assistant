"""RBAC 权限校验 FastAPI 依赖项。

用法：
    @router.get("/orders", dependencies=[Depends(require_perm("order:read"))])
    async def list_orders(): ...

    @router.post("/refund", dependencies=[Depends(require_role("agent"))])
    async def create_refund(): ...

get_current_user 从 Authorization: Bearer <token> 解析 access token，
返回 CurrentUser(id, tenant_id, roles, permissions)。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt import verify_token
from exceptions import BusinessException, ErrorCode

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """从 access token 解析的用户上下文。"""

    __slots__ = ("id", "tenant_id", "roles", "permissions")

    def __init__(self, user_id: int, tenant_id: int, roles: list[str], permissions: list[str]):
        self.id = user_id
        self.tenant_id = tenant_id
        self.roles = roles
        self.permissions = permissions

    def has_perm(self, perm: str) -> bool:
        return perm in self.permissions

    def has_role(self, role: str) -> bool:
        return role in self.roles


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> CurrentUser:
    """从 Bearer token 解析当前用户；不带 token 或 token 无效直接 401。"""
    if credentials is None:
        raise BusinessException(ErrorCode.AUTH_TOKEN_INVALID, message="缺少 Authorization 头")

    payload = verify_token(credentials.credentials, expected_type="access")

    try:
        user_id = int(payload["sub"])
        tenant_id = int(payload["tid"])
        roles: list[str] = payload.get("roles", [])
        permissions: list[str] = payload.get("perms", [])
    except (KeyError, ValueError) as exc:
        raise BusinessException(ErrorCode.AUTH_TOKEN_INVALID, message="token payload 格式错误") from exc

    return CurrentUser(user_id=user_id, tenant_id=tenant_id, roles=roles, permissions=permissions)


def require_perm(perm: str):
    """FastAPI 依赖工厂：验证用户持有指定权限点。"""

    async def _dep(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not user.has_perm(perm):
            raise BusinessException(ErrorCode.PERM_FORBIDDEN, message=f"缺少权限 {perm}")
        return user

    return Depends(_dep)


def require_role(role: str):
    """FastAPI 依赖工厂：验证用户持有指定角色。"""

    async def _dep(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not user.has_role(role):
            raise BusinessException(ErrorCode.PERM_FORBIDDEN, message=f"需要角色 {role}")
        return user

    return Depends(_dep)


__all__ = [
    "CurrentUser",
    "get_current_user",
    "require_perm",
    "require_role",
]
