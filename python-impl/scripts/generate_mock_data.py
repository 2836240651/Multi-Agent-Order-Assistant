"""scripts/generate_mock_data.py：中规模 mock 数据生成（幂等）。

生成规模：
- 5 租户（bootstrap.py 已创建则复用）
- 1000 用户（每租户 200，按角色分配）
- 10000 订单（状态分布：delivered 60% / shipped 20% / pending 10% / cancelled 10%）
- 5000 工单（类型：refund 60% / exchange 20% / address_change 20%）
  - 含 200 条高风险退款特征基线
- 1000 KB 文档（W1 已有则跳过）

用法：
    cd python-impl
    python -m scripts.generate_mock_data
    python -m scripts.generate_mock_data --dry-run
    python -m scripts.generate_mock_data --users 100 --orders 500 --tickets 200
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "dev")

logger = logging.getLogger(__name__)

# ── 数据配置 ────────────────────────────────────────────────────

TENANT_CODES = ["tenant-a", "tenant-b", "tenant-c", "tenant-d", "tenant-e"]

PRODUCTS = [
    "蓝牙耳机", "无线充电器", "机械键盘", "智能手表", "便携音箱",
    "笔记本支架", "USB-C 扩展坞", "电竞鼠标", "降噪耳机", "移动电源",
    "手机壳", "数据线", "充电头", "屏幕保护膜", "车载支架",
    "运动手环", "摄像头", "路由器", "固态硬盘", "内存条",
]

REFUND_REASONS = [
    "7天无理由退货", "质量问题", "收到商品与描述不符", "发错商品",
    "商品损坏", "不喜欢/不想要", "尺寸不合适", "颜色不对",
    "功能异常", "配件缺失", "包装破损", "已过保质期",
]

ADDRESSES = [
    "北京市朝阳区建国路88号", "上海市浦东新区陆家嘴环路1000号",
    "广州市天河区体育西路191号", "深圳市南山区科技园南区",
    "杭州市西湖区文三路478号", "成都市武侯区天府大道北段1700号",
    "武汉市洪山区珞瑜路1037号", "南京市鼓楼区中央路1号",
    "重庆市渝中区解放碑步行街", "西安市雁塔区高新路25号",
]

TICKET_STATUSES = ["open", "in_progress", "pending_review", "resolved", "closed"]
ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled", "refunded"]

# ── 工具函数 ────────────────────────────────────────────────────

def _random_phone() -> str:
    return f"1{random.choice('3456789')}{random.randint(100000000, 999999999)}"


def _random_date(start_days_ago: int = 180, end_days_ago: int = 0) -> datetime:
    delta = random.randint(end_days_ago, start_days_ago)
    return datetime.now(timezone.utc) - timedelta(
        days=delta, hours=random.randint(0, 23), minutes=random.randint(0, 59)
    )


def _random_amount(category: str = "normal") -> float:
    if category == "high_risk":
        return round(random.uniform(1000, 9999), 2)
    return round(random.uniform(9.9, 899.9), 2)


# ── 核心生成逻辑 ────────────────────────────────────────────────

async def generate(
    *,
    users_per_tenant: int = 200,
    total_orders: int = 10000,
    total_tickets: int = 5000,
    total_kb: int = 1000,
    dry_run: bool = False,
) -> dict:
    """生成 mock 数据。返回统计摘要。"""
    from sqlalchemy import select, func as sa_func
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from db.base import Base
    from db.models import Tenant, User, Order, Ticket, UserRole, Role, KnowledgeDoc
    from auth.user_service import hash_password
    from config import settings

    engine = create_async_engine(settings.PG_DSN, future=True, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    if not dry_run:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("tables created / verified")

    stats = {"tenants": 0, "users": 0, "orders": 0, "tickets": 0, "kb_docs": 0}

    async with Session() as session:
        # ── 租户 ────────────────────────────────────────────────
        tenant_ids: list[int] = []
        for code in TENANT_CODES:
            result = await session.execute(select(Tenant).where(Tenant.code == code))
            t = result.scalar_one_or_none()
            if t:
                tenant_ids.append(t.id)
            else:
                if not dry_run:
                    t = Tenant(code=code, name=f"租户 {code}")
                    session.add(t)
                    await session.flush()
                    tenant_ids.append(t.id)
                stats["tenants"] += 1

        if not tenant_ids:
            tenant_ids = list(range(1, len(TENANT_CODES) + 1))

        # ── 角色 ID ─────────────────────────────────────────────
        role_result = await session.execute(select(Role))
        role_map = {r.name: r.id for r in role_result.scalars().all()}
        customer_role_id = role_map.get("customer", 1)

        # ── 用户 ────────────────────────────────────────────────
        pw_hash = hash_password("123456")
        user_ids_by_tenant: dict[int, list[int]] = {tid: [] for tid in tenant_ids}

        for tid in tenant_ids:
            # 检查已有用户数
            count_result = await session.execute(
                select(sa_func.count()).select_from(User).where(User.tenant_id == tid)
            )
            existing = count_result.scalar() or 0
            to_create = max(0, users_per_tenant - existing)

            for i in range(to_create):
                suffix = str(uuid.uuid4().hex[:6])
                u = User(
                    username=f"user_{tid}_{suffix}",
                    password_hash=pw_hash,
                    display_name=f"用户_{tid}_{i+1:04d}",
                    email=f"user_{tid}_{i+1}@example.com",
                    tenant_id=tid,
                    status=1,
                )
                session.add(u)
                if (i + 1) % 200 == 0:
                    await session.flush()

            await session.flush()

            # 收集该租户所有用户 ID
            uid_result = await session.execute(
                select(User.id).where(User.tenant_id == tid)
            )
            user_ids_by_tenant[tid] = [row[0] for row in uid_result.all()]
            stats["users"] += to_create

        # ── 订单 ────────────────────────────────────────────────
        all_user_ids = [uid for uids in user_ids_by_tenant.values() for uid in uids]
        if not all_user_ids:
            all_user_ids = list(range(1, 101))

        orders_per_tenant = total_orders // len(tenant_ids)
        for tid in tenant_ids:
            uids = user_ids_by_tenant.get(tid, all_user_ids[:10])
            for i in range(orders_per_tenant):
                status = random.choices(
                    ORDER_STATUSES, weights=[5, 15, 20, 40, 10, 10], k=1
                )[0]
                created = _random_date()
                delivered = (
                    created + timedelta(days=random.randint(1, 7))
                    if status == "delivered"
                    else None
                )
                o = Order(
                    order_no=f"ORD-{tid}-{uuid.uuid4().hex[:8].upper()}",
                    user_id=random.choice(uids),
                    tenant_id=tid,
                    status=status,
                    total_amount=_random_amount(),
                    item_count=random.randint(1, 5),
                    shipping_address=random.choice(ADDRESSES),
                    product_name=random.choice(PRODUCTS),
                    delivered_at=delivered,
                    created_at=created,
                )
                session.add(o)
                if (i + 1) % 500 == 0:
                    await session.flush()
            stats["orders"] += orders_per_tenant

        await session.flush()

        # ── 工单 ────────────────────────────────────────────────
        tickets_per_tenant = total_tickets // len(tenant_ids)
        ticket_types = ["refund", "exchange", "address_change"]
        type_weights = [60, 20, 20]

        for tid in tenant_ids:
            uids = user_ids_by_tenant.get(tid, all_user_ids[:10])

            # 获取该租户的订单 ID
            order_result = await session.execute(
                select(Order.id).where(Order.tenant_id == tid).limit(2000)
            )
            order_ids = [row[0] for row in order_result.all()] or [None]

            for i in range(tickets_per_tenant):
                t_type = random.choices(ticket_types, weights=type_weights, k=1)[0]
                t_status = random.choices(
                    TICKET_STATUSES, weights=[20, 15, 10, 30, 25], k=1
                )[0]

                # 高风险退款基线：前 200 条退款工单
                is_high_risk = t_type == "refund" and i < 40
                amount = _random_amount("high_risk" if is_high_risk else "normal")

                created = _random_date()
                closed = (
                    created + timedelta(days=random.randint(0, 3))
                    if t_status in ("resolved", "closed")
                    else None
                )

                risk_score = None
                risk_decision = None
                if t_type == "refund":
                    risk_score = round(random.uniform(10, 95), 1) if random.random() < 0.3 else None
                    if risk_score:
                        risk_decision = "reject" if risk_score >= 90 else ("review" if risk_score >= 60 else "pass")

                tk = Ticket(
                    ticket_no=f"TK-{tid}-{uuid.uuid4().hex[:8].upper()}",
                    order_id=random.choice(order_ids),
                    user_id=random.choice(uids),
                    tenant_id=tid,
                    type=t_type,
                    status=t_status,
                    amount=amount,
                    reason=random.choice(REFUND_REASONS),
                    risk_score=risk_score,
                    risk_decision=risk_decision,
                    closed_at=closed,
                    created_at=created,
                )
                session.add(tk)
                if (i + 1) % 500 == 0:
                    await session.flush()
            stats["tickets"] += tickets_per_tenant

        # ── KB 文档 ──────────────────────────────────────────────
        kb_categories = ["policy", "logistics", "faq", "promotion"]
        kb_templates = {
            "policy": [
                ("退换货政策", "7天无理由退货：自签收之日起7天内可申请无理由退货。商品需保持原包装完好，不影响二次销售。退货运费由买家承担（质量问题除外）。"),
                ("保修政策", "本店商品均享受国家三包政策。电子产品保修期为1年，配件类商品保修期为3个月。保修期内非人为损坏免费维修或换新。"),
                ("退款时效", "退款申请审核通过后，1-3个工作日内原路退回。银行卡退款可能需要额外3-5个工作日到账。"),
            ],
            "logistics": [
                ("配送范围", "全国范围内均可配送（港澳台及偏远地区除外）。默认快递为顺丰/京东/中通，特殊商品可能使用专线物流。"),
                ("发货时效", "普通商品48小时内发货，定制商品5-7个工作日发货。大促期间可能延迟1-2天。"),
            ],
            "faq": [
                ("如何申请退款", "登录账户 → 我的订单 → 找到对应订单 → 点击「申请退款」 → 选择退款原因 → 提交申请。客服将在24小时内审核。"),
                ("如何修改订单地址", "订单未发货前可在订单详情页直接修改地址。已发货订单需联系客服协助拦截修改，可能产生额外运费。"),
            ],
            "promotion": [
                ("会员积分规则", "每消费1元积1分，积分可兑换优惠券。普通会员1000积分=10元券，金卡会员800积分=10元券。积分有效期1年。"),
                ("新人专享优惠", "新注册用户首单立减20元（满99元可用）。注册后7天内有效，每个账号限领一次。"),
            ],
        }

        docs_per_tenant = total_kb // (len(tenant_ids) + 1)  # +1 for global docs

        # 全局 KB 文档
        for cat in kb_categories:
            templates = kb_templates[cat]
            for j in range(docs_per_tenant // len(kb_categories)):
                title, content = templates[j % len(templates)]
                if not dry_run:
                    doc = KnowledgeDoc(
                        tenant_id=None,  # 全局可见
                        doc_no=f"KB-GLOBAL-{cat[:3].upper()}-{j+1:04d}",
                        title=f"{title}（全局{ j+1}）",
                        category=cat,
                        effective_from=_random_date(30, 0),
                        effective_to=_random_date(365, 30) if random.random() < 0.1 else None,
                    )
                    session.add(doc)
                stats["kb_docs"] += 1

        # 租户级 KB 文档
        for tid in tenant_ids:
            for cat in kb_categories:
                templates = kb_templates[cat]
                for j in range(docs_per_tenant // len(kb_categories)):
                    title, content = templates[j % len(templates)]
                    if not dry_run:
                        doc = KnowledgeDoc(
                            tenant_id=tid,
                            doc_no=f"KB-{tid}-{cat[:3].upper()}-{j+1:04d}",
                            title=f"{title}（租户{tid}-{j+1}）",
                            category=cat,
                            effective_from=_random_date(30, 0),
                            effective_to=_random_date(365, 30) if random.random() < 0.1 else None,
                        )
                        session.add(doc)
                    stats["kb_docs"] += 1

        if not dry_run:
            await session.flush()

        if not dry_run:
            await session.commit()
            logger.info("mock data committed")
        else:
            logger.info("[dry-run] nothing committed")

    await engine.dispose()
    return stats


# ── CLI ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="RetailGuard mock data generator")
    parser.add_argument("--users", type=int, default=200, help="每租户用户数")
    parser.add_argument("--orders", type=int, default=10000, help="总订单数")
    parser.add_argument("--tickets", type=int, default=5000, help="总工单数")
    parser.add_argument("--kb", type=int, default=1000, help="总 KB 文档数")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s :: %(message)s",
    )

    stats = asyncio.run(generate(
        users_per_tenant=args.users,
        total_orders=args.orders,
        total_tickets=args.tickets,
        total_kb=args.kb,
        dry_run=args.dry_run,
    ))

    print(f"\n{'='*50}")
    print("Mock 数据生成完成")
    print(f"{'='*50}")
    print(f"  租户:  {stats['tenants']}")
    print(f"  用户:  {stats['users']}")
    print(f"  订单:  {stats['orders']}")
    print(f"  工单:  {stats['tickets']}")
    print(f"  KB:    {stats['kb_docs']}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
