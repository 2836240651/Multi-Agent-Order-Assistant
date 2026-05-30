"""db 模块对外接口。"""
from .base import Base, GlobalMixin, OptimisticLockMixin, TenantMixin, TimestampMixin
from .models import AuditLog, KnowledgeDoc, Order, Tenant, Ticket, User
from .session import (
    async_session,
    get_async_engine,
    get_async_session_factory,
    get_sync_engine,
    get_sync_session_factory,
    sync_session,
)
from .tenant_context import (
    current_tenant_code,
    current_tenant_id,
    is_tenant_filter_skipped,
    set_current_tenant,
    skip_filter_reason,
    skip_tenant_filter,
)

__all__ = [
    "Base",
    "TenantMixin",
    "GlobalMixin",
    "TimestampMixin",
    "OptimisticLockMixin",
    "Tenant",
    "User",
    "Order",
    "Ticket",
    "KnowledgeDoc",
    "AuditLog",
    "async_session",
    "sync_session",
    "get_async_engine",
    "get_sync_engine",
    "get_async_session_factory",
    "get_sync_session_factory",
    "set_current_tenant",
    "current_tenant_id",
    "current_tenant_code",
    "is_tenant_filter_skipped",
    "skip_filter_reason",
    "skip_tenant_filter",
]
