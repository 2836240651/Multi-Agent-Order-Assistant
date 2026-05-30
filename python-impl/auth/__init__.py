"""auth 模块：JWT 工具 + RBAC 依赖项 + 用户服务。

设计.md §6.1：HS256 双 token（access 30min + refresh 7d）；RBAC 4 角色；
5 次失败锁定（Redis 计数器 TTL 15min）。
"""
from auth.jwt import create_access_token, create_refresh_token, verify_token
from auth.permissions import CurrentUser, get_current_user, require_perm, require_role
from auth.user_service import (
    authenticate_user,
    get_user_roles_and_perms,
    hash_password,
    verify_password,
)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "CurrentUser",
    "get_current_user",
    "require_perm",
    "require_role",
    "authenticate_user",
    "get_user_roles_and_perms",
    "hash_password",
    "verify_password",
]
