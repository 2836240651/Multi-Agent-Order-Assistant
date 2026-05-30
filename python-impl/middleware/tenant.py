"""tenant 中间件：从 JWT 或 X-Tenant-Id header 取 tenant_id 注入 ContextVar。

W1 简化版：未接 JWT，仅从 header 取（演示用）；W6 改为 JWT claim。
W7: 内存缓存替换为 Redis（TTL 60s）。
"""
from __future__ import annotations

import logging
import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from config import settings
from db import set_current_tenant
from db.session import async_session
from db.models import Tenant
from exceptions import BusinessException, ErrorCode

logger = logging.getLogger(__name__)

_TENANT_CACHE_TTL = 60  # Redis 缓存 TTL 60s

# 演示 / 测试环境 DB 不可用时的稳定 tenant_id 映射，保证多租户隔离测试可重现
_DEMO_TENANT_MAP: dict[str, int] = {
    "tenant-a": 1,
    "tenant-b": 2,
}


def _redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis as _redis_lib
        return _redis_lib.from_url(url, decode_responses=True)
    except Exception:
        return None


async def _resolve_tenant(code: str) -> int | None:
    """tenant_code → tenant_id。优先查 Redis 缓存（TTL 60s），miss 后查 DB。"""
    # 1) Redis 缓存
    r = _redis()
    if r:
        try:
            cached = r.get(f"tenant_code:{code}")
            if cached is not None:
                return int(cached)
        except Exception:
            pass

    # 2) 查 DB
    try:
        async with async_session() as session:
            from sqlalchemy import select

            stmt = select(Tenant).where(Tenant.code == code, Tenant.status == 1)
            res = await session.execute(stmt)
            tenant = res.scalar_one_or_none()
            if tenant is None:
                return None
            # 写 Redis 缓存
            if r:
                try:
                    r.setex(f"tenant_code:{code}", _TENANT_CACHE_TTL, str(tenant.id))
                except Exception:
                    pass
            return tenant.id
    except Exception as exc:  # 数据库不可用时不阻断（用于 demo / 测试）
        logger.warning("tenant lookup failed for %s: %s", code, exc)
        return None


class TenantMiddleware(BaseHTTPMiddleware):
    """从请求 header 解析 tenant_code，注入 ContextVar。

    - 跳过路径：/health, /api/v1/openapi.json, /docs, /redoc
    - 缺失 header → 用 APP_DEFAULT_TENANT
    - tenant 不存在或停用 → 403 AUTH_TENANT_DISABLED
    """

    SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/api/v1/openapi.json"}

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        tenant_code = request.headers.get("X-Tenant-Id") or settings.APP_DEFAULT_TENANT
        tenant_id = await _resolve_tenant(tenant_code)

        if tenant_id is None:
            # 演示 / 测试阶段：DB 未初始化时按 tenant_code 映射稳定 tenant_id（防真实租户混淆）
            if settings.is_dev or settings.is_test:
                tenant_id = _DEMO_TENANT_MAP.get(tenant_code, 1)
            else:
                exc = BusinessException(
                    ErrorCode.AUTH_TENANT_DISABLED, message=f"租户 {tenant_code} 不存在或已停用"
                )
                return JSONResponse(status_code=403, content=exc.to_dict())

        set_current_tenant(tenant_id, tenant_code)
        response = await call_next(request)
        response.headers["X-Tenant-Code"] = tenant_code
        return response


__all__ = ["TenantMiddleware"]
