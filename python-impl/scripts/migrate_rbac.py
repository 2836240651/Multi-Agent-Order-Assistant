"""RBAC 表迁移脚本：创建 roles / permissions / user_roles / role_permissions，
并写入 4 个默认角色和常用权限点。

运行：APP_ENV=prod python -m scripts.migrate_rbac
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ROLES = [
    {"name": "customer", "display_name": "客户", "description": "普通消费者，只能查询自己的订单和工单"},
    {"name": "agent", "display_name": "客服专员", "description": "处理退换货、工单、知识库查询"},
    {"name": "risk", "display_name": "风控审核员", "description": "查看风控事件、审批高风险工单"},
    {"name": "admin", "display_name": "系统管理员", "description": "全权限，含用户和租户管理"},
]

_PERMISSIONS = [
    {"code": "order:read", "description": "查询订单"},
    {"code": "order:write", "description": "创建/修改订单"},
    {"code": "refund:read", "description": "查询退款申请"},
    {"code": "refund:create", "description": "发起退款申请"},
    {"code": "refund:approve", "description": "审批退款（风控/客服）"},
    {"code": "ticket:read", "description": "查询工单"},
    {"code": "ticket:write", "description": "创建/回复工单"},
    {"code": "ticket:close", "description": "关闭工单"},
    {"code": "risk:read", "description": "查看风控事件"},
    {"code": "risk:review", "description": "人工审核风控决策"},
    {"code": "kb:read", "description": "查询知识库"},
    {"code": "kb:write", "description": "上传/编辑知识库"},
    {"code": "user:read", "description": "查询用户信息"},
    {"code": "user:write", "description": "创建/修改用户"},
    {"code": "admin:all", "description": "超级权限（所有操作）"},
]

# 角色 → 权限点映射
_ROLE_PERMS: dict[str, list[str]] = {
    "customer": ["order:read", "refund:read", "refund:create", "ticket:read", "ticket:write", "kb:read"],
    "agent": [
        "order:read", "refund:read", "refund:create", "refund:approve",
        "ticket:read", "ticket:write", "ticket:close", "kb:read", "kb:write",
    ],
    "risk": ["order:read", "refund:read", "risk:read", "risk:review", "ticket:read"],
    "admin": ["admin:all"],
}


def run_migration() -> None:
    """执行同步迁移（适合脚本/CI 环境）。"""
    from sqlalchemy import text
    from db.session import get_sync_engine, sync_session
    from db.base import Base
    from db.models import Role, Permission, RolePermission  # noqa: F401 — registers tables

    engine = get_sync_engine()

    # 建表（幂等）
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("tables created (if not exists)")

    with sync_session() as session:
        # 插入角色
        role_map: dict[str, int] = {}
        for r in _ROLES:
            existing = session.execute(
                text("SELECT id FROM roles WHERE name = :name"), {"name": r["name"]}
            ).scalar_one_or_none()
            if existing is None:
                session.execute(
                    text("INSERT INTO roles (name, display_name, description) VALUES (:name, :dn, :desc)"),
                    {"name": r["name"], "dn": r["display_name"], "desc": r["description"]},
                )
                session.flush()
                existing = session.execute(
                    text("SELECT id FROM roles WHERE name = :name"), {"name": r["name"]}
                ).scalar_one()
            role_map[r["name"]] = existing
        logger.info("roles seeded: %s", list(role_map))

        # 插入权限
        perm_map: dict[str, int] = {}
        for p in _PERMISSIONS:
            existing = session.execute(
                text("SELECT id FROM permissions WHERE code = :code"), {"code": p["code"]}
            ).scalar_one_or_none()
            if existing is None:
                session.execute(
                    text("INSERT INTO permissions (code, description) VALUES (:code, :desc)"),
                    {"code": p["code"], "desc": p["description"]},
                )
                session.flush()
                existing = session.execute(
                    text("SELECT id FROM permissions WHERE code = :code"), {"code": p["code"]}
                ).scalar_one()
            perm_map[p["code"]] = existing
        logger.info("permissions seeded: %s", list(perm_map))

        # 关联角色-权限
        for role_name, perm_codes in _ROLE_PERMS.items():
            rid = role_map.get(role_name)
            if rid is None:
                continue
            for code in perm_codes:
                pid = perm_map.get(code)
                if pid is None:
                    continue
                existing = session.execute(
                    text("SELECT id FROM role_permissions WHERE role_id=:rid AND permission_id=:pid"),
                    {"rid": rid, "pid": pid},
                ).scalar_one_or_none()
                if existing is None:
                    session.execute(
                        text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"),
                        {"rid": rid, "pid": pid},
                    )
        logger.info("role_permissions linked")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
    print("RBAC migration done.")
