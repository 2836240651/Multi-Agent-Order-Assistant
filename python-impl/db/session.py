"""SQLAlchemy session 工厂 + 全局 event listener：自动按 tenant_id 过滤。

实现要点（对应设计.md §4.3）：
- 全局 do_orm_execute event 监听所有 select
- TenantMixin 类自动追加 `cls.tenant_id == current_tenant_id()`
- GlobalMixin 跳过
- skip_tenant_filter() 上下文内跳过（用于管理员审计 / 系统脚本）
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from config import settings
from db.base import GlobalMixin, TenantMixin
from db.tenant_context import current_tenant_id, is_tenant_filter_skipped

logger = logging.getLogger(__name__)


_async_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None
_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None


def get_async_engine() -> AsyncEngine:
    global _async_engine
    if _async_engine is None:
        dsn = settings.PG_DSN
        if dsn.startswith("sqlite"):
            # SQLite 本地模式：零外部依赖，适合本地开发 / 面试 demo
            import aiosqlite  # noqa: F401 — 确保已安装
            import pathlib
            db_path = dsn.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
            pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            _async_engine = create_async_engine(dsn, echo=False)
        else:
            _async_engine = create_async_engine(dsn, future=True, pool_pre_ping=True, echo=False)
    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _async_session_factory


def get_sync_engine() -> Engine:
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine

        dsn = settings.PG_DSN_SYNC
        kwargs = {"future": True, "echo": False}
        if not dsn.startswith("sqlite"):
            kwargs["pool_pre_ping"] = True
        _sync_engine = create_engine(dsn, **kwargs)
    return _sync_engine


def get_sync_session_factory() -> sessionmaker[Session]:
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(
            bind=get_sync_engine(), class_=Session, expire_on_commit=False, autoflush=False
        )
    return _sync_session_factory


# === 自动 tenant 过滤的 event listener ===

def _install_tenant_filter() -> None:
    """注册全局 do_orm_execute event，所有 select 都按 tenant 过滤。"""

    @event.listens_for(Session, "do_orm_execute")
    def _filter_tenant(execute_state) -> None:  # type: ignore[no-untyped-def]
        if not execute_state.is_select:
            return
        if is_tenant_filter_skipped():
            return
        tid = current_tenant_id()
        if tid is None:
            # 无 tenant 上下文：仅在 select 上不强制（脚本/启动期）；
            # 业务路径会在 middleware 层显式 set。
            return
        # 仅对 TenantMixin 派生类生效，且自动忽略 GlobalMixin。
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantMixin,
                lambda cls: cls.tenant_id == tid,
                include_aliases=True,
            )
        )

    @event.listens_for(AsyncSession.sync_session_class, "do_orm_execute")
    def _filter_tenant_async(execute_state) -> None:  # type: ignore[no-untyped-def]
        # AsyncSession 内部使用 sync Session；事件名一致，绑定一次即可
        # 这里留空避免重复绑定；event.listens_for 已对 Session 类生效
        return


_install_tenant_filter()


# === Session 上下文管理器 ===

@asynccontextmanager
async def async_session() -> AsyncIterator[AsyncSession]:
    """异步 session 上下文。"""
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def sync_session() -> Iterator[Session]:
    """同步 session 上下文（脚本/Celery 用）。"""
    factory = get_sync_session_factory()
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


__all__ = [
    "get_async_engine",
    "get_async_session_factory",
    "get_sync_engine",
    "get_sync_session_factory",
    "async_session",
    "sync_session",
    "GlobalMixin",
]
