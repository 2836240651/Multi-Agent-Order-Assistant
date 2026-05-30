"""scripts/bootstrap.py：幂等初始化脚本。

创建：
- 5 个租户（tenant-a … tenant-e）
- 4 个角色（customer / agent / risk / admin）
- 30 个权限点（按资源:动作格式）
- 角色-权限绑定
- 每个租户各创建 4 个 demo 用户（各角色一名）

幂等：已存在的记录跳过，不重复创建。

用法：
    cd python-impl
    python -m scripts.bootstrap
    python -m scripts.bootstrap --dry-run   # 只打印，不写库
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# ── 路径修正 ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "dev")

logger = logging.getLogger(__name__)

# ── 数据定义 ────────────────────────────────────────────────────

TENANTS = [
    {"code": "tenant-a", "name": "优选商城（A）"},
    {"code": "tenant-b", "name": "科技直营（B）"},
    {"code": "tenant-c", "name": "时尚穿搭（C）"},
    {"code": "tenant-d", "name": "数码电器（D）"},
    {"code": "tenant-e", "name": "居家生活（E）"},
]

ROLES = [
    {"name": "customer",  "display_name": "顾客"},
    {"name": "agent",     "display_name": "客服专员"},
    {"name": "risk",      "display_name": "风控专员"},
    {"name": "admin",     "display_name": "管理员"},
]

PERMISSIONS = [
    # chat
    ("chat:send",          "发起对话"),
    # order
    ("order:read",         "查看订单"),
    ("order:update",       "修改订单"),
    # ticket
    ("ticket:create",      "创建工单"),
    ("ticket:read",        "查看工单"),
    ("ticket:update",      "更新工单"),
    ("ticket:close",       "关闭工单"),
    # refund
    ("refund:apply",       "申请退款"),
    ("refund:read",        "查看退款"),
    ("refund:approve",     "审批退款"),
    # knowledge
    ("knowledge:read",     "查询知识库"),
    ("knowledge:write",    "维护知识库"),
    # review / risk
    ("review:read",        "查看待审列表"),
    ("review:approve",     "风控审批"),
    ("risk:read",          "查看风控结果"),
    ("risk:write",         "配置风控权重"),
    # admin
    ("admin:cost",         "查看成本面板"),
    ("admin:rollout",      "调整灰度权重"),
    ("admin:tenant",       "租户管理"),
    ("admin:user",         "用户管理"),
    ("admin:dlq",          "死信队列管理"),
    # task
    ("task:batch_review",  "触发批量审核"),
    ("task:ingest",        "触发知识库灌库"),
    # eval
    ("eval:run",           "运行评测"),
]

# 角色 → 权限 code 集合
ROLE_PERMS: dict[str, list[str]] = {
    "customer": [
        "chat:send", "order:read", "ticket:create", "ticket:read", "refund:apply", "refund:read", "knowledge:read",
    ],
    "agent": [
        "chat:send",
        "order:read", "order:update",
        "ticket:create", "ticket:read", "ticket:update", "ticket:close",
        "refund:read", "refund:approve",
        "knowledge:read",
        "review:read",
        "task:batch_review",
    ],
    "risk": [
        "order:read",
        "ticket:read",
        "refund:read",
        "review:read", "review:approve",
        "risk:read", "risk:write",
        "admin:dlq",
    ],
    "admin": [p for p, _ in PERMISSIONS],  # 全部权限
}

# 每个租户的 demo 用户（用户名后缀 _{tenant_code[-1]}）
DEMO_USERS_TEMPLATE = [
    {"username_prefix": "customer",  "role": "customer",  "display_prefix": "顾客"},
    {"username_prefix": "agent",     "role": "agent",     "display_prefix": "客服"},
    {"username_prefix": "risk",      "role": "risk",      "display_prefix": "风控"},
    {"username_prefix": "admin",     "role": "admin",     "display_prefix": "管理员"},
]

DEFAULT_PASSWORD = "123456"


# ── 核心逻辑 ────────────────────────────────────────────────────

async def bootstrap(dry_run: bool = False) -> None:
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from db.base import Base
    from db.models import Tenant, User, Role, Permission, UserRole, RolePermission
    from auth.user_service import hash_password
    from config import settings

    dsn = settings.PG_DSN
    # SQLite 本地模式：自动创建目录
    if dsn.startswith("sqlite"):
        import pathlib
        db_path = dsn.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(dsn, echo=False)
    else:
        engine = create_async_engine(dsn, future=True, pool_pre_ping=True)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)

    # ── 建表 ───────────────────────────────────────────────────
    if not dry_run:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("tables created / verified")
    else:
        logger.info("[dry-run] would create tables")

    async with SessionMaker() as session:
        # ── 租户 ────────────────────────────────────────────────
        tenant_map: dict[str, int] = {}
        for td in TENANTS:
            result = await session.execute(
                select(Tenant).where(Tenant.code == td["code"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                tenant_map[td["code"]] = existing.id
                logger.info("tenant exists: %s (id=%d)", td["code"], existing.id)
            else:
                if not dry_run:
                    t = Tenant(code=td["code"], name=td["name"])
                    session.add(t)
                    await session.flush()
                    tenant_map[td["code"]] = t.id
                    logger.info("created tenant: %s (id=%d)", td["code"], t.id)
                else:
                    logger.info("[dry-run] would create tenant: %s", td["code"])
                    tenant_map[td["code"]] = -1

        # ── 权限 ────────────────────────────────────────────────
        perm_map: dict[str, int] = {}
        for code, desc in PERMISSIONS:
            result = await session.execute(
                select(Permission).where(Permission.code == code)
            )
            existing = result.scalar_one_or_none()
            if existing:
                perm_map[code] = existing.id
            else:
                if not dry_run:
                    p = Permission(code=code, description=desc)
                    session.add(p)
                    await session.flush()
                    perm_map[code] = p.id
                    logger.info("created permission: %s", code)
                else:
                    logger.info("[dry-run] would create permission: %s", code)
                    perm_map[code] = -1

        # ── 角色 + 角色-权限 ────────────────────────────────────
        role_map: dict[str, int] = {}
        for rd in ROLES:
            result = await session.execute(
                select(Role).where(Role.name == rd["name"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                role_map[rd["name"]] = existing.id
                logger.info("role exists: %s (id=%d)", rd["name"], existing.id)
            else:
                if not dry_run:
                    r = Role(name=rd["name"], display_name=rd["display_name"])
                    session.add(r)
                    await session.flush()
                    role_map[rd["name"]] = r.id
                    logger.info("created role: %s (id=%d)", rd["name"], r.id)
                else:
                    logger.info("[dry-run] would create role: %s", rd["name"])
                    role_map[rd["name"]] = -1

            role_id = role_map[rd["name"]]
            for perm_code in ROLE_PERMS.get(rd["name"], []):
                perm_id = perm_map.get(perm_code)
                if perm_id is None:
                    continue
                if dry_run:
                    continue
                rp_res = await session.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role_id,
                        RolePermission.permission_id == perm_id,
                    )
                )
                if rp_res.scalar_one_or_none() is None:
                    session.add(RolePermission(role_id=role_id, permission_id=perm_id))

        # ── Demo 用户 ────────────────────────────────────────────
        pw_hash = hash_password(DEFAULT_PASSWORD)
        for tenant_info in TENANTS:
            t_code = tenant_info["code"]
            t_id = tenant_map.get(t_code, -1)
            if t_id == -1:
                continue  # dry-run skip

            suffix = t_code.split("-")[-1]  # "a", "b", ...
            for ut in DEMO_USERS_TEMPLATE:
                uname = f"{ut['username_prefix']}_{suffix}"
                result = await session.execute(
                    select(User).where(User.username == uname, User.tenant_id == t_id)
                )
                existing_user = result.scalar_one_or_none()
                if existing_user:
                    logger.info("user exists: %s@%s", uname, t_code)
                    continue

                if dry_run:
                    logger.info("[dry-run] would create user: %s@%s role=%s", uname, t_code, ut["role"])
                    continue

                u = User(
                    username=uname,
                    password_hash=pw_hash,
                    display_name=f"{ut['display_prefix']}_{suffix.upper()}",
                    tenant_id=t_id,
                    status=1,
                )
                session.add(u)
                await session.flush()

                role_id = role_map.get(ut["role"])
                if role_id and role_id > 0:
                    session.add(UserRole(user_id=u.id, role_id=role_id, tenant_id=t_id))
                logger.info("created user: %s@%s (id=%d) role=%s", uname, t_code, u.id, ut["role"])

        if not dry_run:
            await session.commit()
            logger.info("bootstrap committed.")
        else:
            logger.info("[dry-run] nothing committed.")

    await engine.dispose()


def _print_summary() -> None:
    print("\n╔══════════════════════════════════════════════╗")
    print("║         Bootstrap 完成 — Demo 账号            ║")
    print("╠══════════════════════════════════════════════╣")
    print("║ 密码统一：123456                             ║")
    print("║                                              ║")
    for td in TENANTS:
        suffix = td["code"].split("-")[-1]
        print(f"║  {td['name'][:10]:<12}({td['code']})       ║")
        for ut in DEMO_USERS_TEMPLATE:
            uname = f"{ut['username_prefix']}_{suffix}"
            print(f"║    {uname:<20} [{ut['role']:8}]    ║")
    print("╚══════════════════════════════════════════════╝\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="RetailGuard bootstrap")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s :: %(message)s",
    )

    asyncio.run(bootstrap(dry_run=args.dry_run))
    if not args.dry_run:
        try:
            from rag.bootstrap import ensure_kb_indexed

            stats = ensure_kb_indexed(force=True)
            logger.info("KB indexed after bootstrap: %s", stats)
        except Exception as exc:
            logger.warning("KB ingest after bootstrap skipped: %s", exc)
        _print_summary()


if __name__ == "__main__":
    main()
