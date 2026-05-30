"""SQLAlchemy 模型基类与 mixin。

- Base: declarative base
- TenantMixin: 含 tenant_id 列；被 session event listener 自动加 where 条件
- GlobalMixin: 全局表（roles/permissions）跳过 tenant 过滤
- TimestampMixin: created_at/updated_at
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 2.x declarative base。"""

    metadata_extra: dict[str, Any] = {}


class TimestampMixin:
    """通用 created_at / updated_at 列。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """业务表 mixin：必带 tenant_id；session event listener 自动注入 where。

    设计.md §4.3：所有业务表强制 tenant_id NOT NULL；跨租户查询走 skip_tenant_filter。
    """

    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class GlobalMixin:
    """全局表 mixin（无 tenant_id，比如 roles / permissions）。"""

    __global_table__ = True


class OptimisticLockMixin:
    """乐观锁 mixin。"""

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


__all__ = ["Base", "TimestampMixin", "TenantMixin", "GlobalMixin", "OptimisticLockMixin"]
