"""tenant 上下文管理：ContextVar 存当前请求的 tenant_id；skip_tenant_filter 上下文跳过过滤。

设计.md §4.3 / §7.8：
- 所有业务表查询自动追加 `tenant_id = current` 条件
- 跨租户操作必须显式 `with skip_tenant_filter(reason=...)`，自动写 audit_log
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

logger = logging.getLogger(__name__)


# 当前请求 tenant_id（int）。None 表示未绑定（脚本上下文）。
_current_tenant_id: ContextVar[int | None] = ContextVar(
    "current_tenant_id", default=None
)
# 当前请求 tenant_code（人读）
_current_tenant_code: ContextVar[str | None] = ContextVar(
    "current_tenant_code", default=None
)
# 跳过 tenant 过滤的开关 + 原因
_skip_filter: ContextVar[str | None] = ContextVar("skip_tenant_filter", default=None)


def set_current_tenant(tenant_id: int | None, tenant_code: str | None = None) -> None:
    """在请求中间件中调用，设置当前 tenant 上下文。"""
    _current_tenant_id.set(tenant_id)
    _current_tenant_code.set(tenant_code)


def current_tenant_id() -> int | None:
    return _current_tenant_id.get()


def current_tenant_code() -> str | None:
    return _current_tenant_code.get()


def is_tenant_filter_skipped() -> bool:
    return _skip_filter.get() is not None


def skip_filter_reason() -> str | None:
    return _skip_filter.get()


@contextmanager
def skip_tenant_filter(reason: str) -> Iterator[None]:
    """跳过 tenant 过滤的上下文管理器。强制要求 reason 写入 audit_log。

    用法：
        with skip_tenant_filter("admin_audit"):
            stmt = select(Order)  # 不会被注入 tenant 条件
    """
    if not reason:
        raise ValueError("skip_tenant_filter 必须传入 reason")
    token = _skip_filter.set(reason)
    try:
        logger.info("tenant filter skipped, reason=%s", reason)
        yield
    finally:
        _skip_filter.reset(token)


__all__ = [
    "set_current_tenant",
    "current_tenant_id",
    "current_tenant_code",
    "is_tenant_filter_skipped",
    "skip_filter_reason",
    "skip_tenant_filter",
]
