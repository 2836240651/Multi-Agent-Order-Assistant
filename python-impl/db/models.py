"""数据库 ORM 模型。设计.md §4.2 表 DDL 的 SQLAlchemy 实现。

W1 范围：tenants / users / knowledge_docs / audit_logs。其余表 W3+ 引入。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, GlobalMixin, TenantMixin, TimestampMixin


class Tenant(GlobalMixin, TimestampMixin, Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    quota_qps: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    quota_monthly_token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10_000_000)


class User(TenantMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeDoc(TimestampMixin, Base):
    """KB 文档元数据。注意：tenant_id nullable —— NULL 表示全局可见。

    所以这张表不继承 TenantMixin（避免 NOT NULL）；payload filter 在 vectorstore 内实现。
    """

    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    doc_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    qdrant_collection: Mapped[str] = mapped_column(String(64), default="kb_v1")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )


class Order(TenantMixin, TimestampMixin, Base):
    """订单表。W7 新增，用于 mock 数据生成和压测。"""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    total_amount: Mapped[float] = mapped_column(nullable=False, default=0.0)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    shipping_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderItem(TenantMixin, TimestampMixin, Base):
    """订单明细表。"""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    price: Mapped[float] = mapped_column(nullable=False, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Ticket(TenantMixin, TimestampMixin, Base):
    """工单表。W7 新增，覆盖退款/换货/地址变更等售后场景。"""

    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="refund")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    amount: Mapped[float] = mapped_column(nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_agent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(nullable=True)
    risk_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Refund(TenantMixin, TimestampMixin, Base):
    """退款记录表。独立于 Ticket，用于跟踪退款全生命周期。"""

    __tablename__ = "refunds"
    __table_args__ = (
        Index("ix_refunds_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    refund_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    ticket_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[float] = mapped_column(nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")
    risk_score: Mapped[float | None] = mapped_column(nullable=True)
    risk_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(TenantMixin, TimestampMixin, Base):
    """会话消息表。用于存储坐席和客户的对话记录。"""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_tenant_thread", "tenant_id", "thread_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AuditLog(TimestampMixin, Base):
    """审计日志。跨租户 / 管理员操作必须落这里。

    不继承 TenantMixin：审计本身要能跨租户查询，tenant_id nullable。
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Role(GlobalMixin, TimestampMixin, Base):
    """RBAC 角色表（全局，不含 tenant_id）。预置：customer / agent / risk / admin。"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    permissions: Mapped[list["Permission"]] = relationship(
        "Permission", secondary="role_permissions", back_populates="roles", lazy="selectin"
    )


class Permission(GlobalMixin, Base):
    """权限点表（全局）。格式：<resource>:<action>，如 order:read、refund:approve。"""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary="role_permissions", back_populates="permissions", lazy="selectin"
    )


class UserRole(TenantMixin, Base):
    """用户-角色多对多关联（业务表，含 tenant_id）。"""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "role_id", name="uq_user_roles"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)


class RolePermission(GlobalMixin, Base):
    """角色-权限多对多关联（全局）。"""

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permissions"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)


__all__ = [
    "Tenant", "User", "KnowledgeDoc", "Order", "OrderItem", "Ticket",
    "Refund", "Message", "AuditLog", "Role", "Permission", "UserRole",
    "RolePermission",
]
