from __future__ import annotations

import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "commerce.db"

CITIES = [
    ("北京市", ["朝阳区", "海淀区", "东城区", "西城区", "丰台区", "石景山区"]),
    ("上海市", ["浦东新区", "黄浦区", "静安区", "徐汇区", "长宁区", "普陀区"]),
    ("广州市", ["天河区", "越秀区", "海珠区", "白云区", "番禺区"]),
    ("深圳市", ["福田区", "南山区", "宝安区", "龙岗区", "罗湖区"]),
    ("杭州市", ["西湖区", "上城区", "下城区", "拱墅区", "滨江区"]),
    ("南京市", ["鼓楼区", "玄武区", "秦淮区", "建邺区", "栖霞区"]),
    ("成都市", ["锦江区", "青羊区", "金牛区", "武侯区", "成华区"]),
    ("武汉市", ["江汉区", "江岸区", "武昌区", "洪山区", "汉阳区"]),
    ("西安市", ["新城区", "碑林区", "莲湖区", "雁塔区", "未央区"]),
    ("苏州市", ["姑苏区", "虎丘区", "吴中区", "相城区", "工业园区"]),
    ("天津市", ["和平区", "河西区", "南开区", "河北区", "红桥区"]),
    ("重庆市", ["渝中区", "江北区", "南岸区", "沙坪坝区", "九龙坡区"]),
    ("长沙市", ["芙蓉区", "天心区", "岳麓区", "开福区", "雨花区"]),
    ("郑州市", ["金水区", "二七区", "中原区", "管城区", "惠济区"]),
    ("青岛市", ["市南区", "市北区", "李沧区", "崂山区", "城阳区"]),
    ("宁波市", ["海曙区", "江北区", "镇海区", "北仑区", "鄞州区"]),
    ("厦门市", ["思明区", "湖里区", "集美区", "海沧区", "同安区"]),
    ("大连市", ["中山区", "西岗区", "沙河口区", "甘井子区", "高新园区"]),
    ("沈阳市", ["和平区", "沈河区", "皇姑区", "大东区", "铁西区"]),
    ("济南市", ["历下区", "市中区", "槐荫区", "天桥区", "历城区"]),
]

PRODUCTS = [
    ("Smart Speaker", 299.00, 0.1),
    ("Wireless Earbuds", 159.00, 0.15),
    ("USB-C Hub", 89.00, 0.12),
    ("Mechanical Keyboard", 399.00, 0.08),
    ("Ergonomic Mouse", 199.00, 0.1),
    ("Laptop Stand", 1399.00, 0.05),
    ("Monitor Arm", 599.00, 0.06),
    ("Webcam HD", 259.00, 0.1),
    ("Desk Lamp LED", 129.00, 0.15),
    ("Phone Stand", 49.00, 0.2),
    ("Cable Management Kit", 39.00, 0.25),
    ("Portable SSD 1TB", 699.00, 0.07),
    ("Wireless Charger", 79.00, 0.18),
    ("Smart Watch", 1299.00, 0.04),
    ("Fitness Tracker", 399.00, 0.09),
    ("Portable Speaker", 199.00, 0.12),
    ("Tablet Stand", 69.00, 0.2),
    ("Mouse Pad XL", 59.00, 0.22),
    ("USB Microphone", 349.00, 0.08),
    ("Ring Light", 179.00, 0.11),
    ("Laptop Bag", 229.00, 0.1),
    ("Travel Adapter", 89.00, 0.15),
    ("Power Bank 20000mAh", 149.00, 0.12),
    ("Screen Protector", 29.00, 0.3),
    ("Phone Case", 59.00, 0.25),
    ("Tablet Case", 99.00, 0.18),
    ("Stylus Pen", 129.00, 0.1),
    ("Car Phone Mount", 49.00, 0.25),
    ("Bike Phone Mount", 39.00, 0.28),
    ("Selfie Stick", 79.00, 0.2),
]

STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled", "refunded"]
STATUS_WEIGHTS = [0.05, 0.1, 0.25, 0.4, 0.1, 0.1]

USER_IDS = [f"user_{i:04d}" for i in range(1, 301)]

EXPRESS_COMPANIES = [
    ("顺丰速运", "SF"),
    ("中通快递", "ZTO"),
    ("圆通速递", "YTO"),
    ("韵达快递", "YD"),
    ("申通快递", "STO"),
    ("京东物流", "JD"),
    ("邮政快递", "EMS"),
    ("极兔速递", "JTSD"),
]

LOGISTICS_STATUSES = [
    "pending",        # 待发货
    "picked_up",      # 已揽收
    "in_transit",     # 运输中
    "out_for_delivery", # 派送中
    "delivered",       # 已签收
    "returned",       # 退回了
    "exception",      # 异常
]

LOGISTICS_STATUS_MAP = {
    "pending": "pending",
    "processing": "picked_up",
    "shipped": "in_transit",
    "delivered": "delivered",
    "cancelled": "returned",
    "refunded": "returned",
}

TRACKING_DESCRIPTIONS = {
    "pending": ["订单已创建，等待发货"],
    "picked_up": ["快递员已揽收", "包裹已发出", "已离开商家仓库"],
    "in_transit": ["包裹运输中", "到达分拨中心", "离开分拨中心", "运输途中", "途经某某转运中心"],
    "out_for_delivery": ["包裹正在派送中", "快递员正在派送", "请保持电话畅通"],
    "delivered": ["包裹已签收", "签收人：本人", "已签收，感谢使用"],
    "returned": ["包裹已退回", "退回原因：用户拒收", "已退回商家"],
    "exception": ["包裹异常", "联系收件人未果", "地址不详"],
}


def random_address() -> str:
    province, districts = random.choice(CITIES)
    district = random.choice(districts)
    street_num = random.randint(1, 999)
    return f"{province}{district}{street_num}号"


def random_date(days_back: int = 90) -> str:
    return (datetime.now() - timedelta(days=random.randint(0, days_back))).strftime("%Y-%m-%d %H:%M:%S")


def generate_orders(n: int = 1000) -> list[tuple]:
    orders = []
    for i in range(1, n + 1):
        order_date = datetime.now() - timedelta(days=random.randint(0, 90))
        order_id = f"ORD-{order_date.strftime('%Y%m%d')}-{i:04d}"
        user_id = random.choice(USER_IDS)
        product_name, base_price, discount_rate = random.choice(PRODUCTS)
        final_price = round(base_price * (1 - discount_rate), 2)
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        address = random_address()
        order_date_str = order_date.strftime("%Y-%m-%d %H:%M:%S")

        if status == "delivered":
            deliver_date = order_date + timedelta(days=random.randint(3, 7))
            deliver_date_str = deliver_date.strftime("%Y-%m-%d %H:%M:%S")
        else:
            deliver_date_str = None

        can_update_address = status in ("pending", "processing")
        refund_eligible = status in ("pending", "processing", "shipped") or (
            status == "delivered" and (datetime.now() - deliver_date).days <= 7
        )

        orders.append((
            order_id, user_id, product_name, final_price, status, address,
            order_date_str, deliver_date_str, can_update_address, refund_eligible
        ))
    return orders


def generate_tickets(n: int = 50) -> list[tuple]:
    tickets = []
    priorities = ["low", "medium", "high"]
    categories = ["refund", "address_change", "product_inquiry", "complaint", "general"]
    actions = ["refund_request", "address_update", "order_inquiry", "escalation", "general_inquiry"]
    statuses = ["created", "pending", "in_progress", "resolved", "closed"]

    for i in range(1, n + 1):
        ticket_id = f"TK-{datetime.now().strftime('%Y%m%d')}-{i:04d}"
        user_id = random.choice(USER_IDS)
        priority = random.choice(priorities)
        category = random.choice(categories)
        action = random.choice(actions)
        status = random.choice(statuses)
        created_at = random_date(60)
        updated_at = (datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S") + timedelta(hours=random.randint(1, 72))).strftime("%Y-%m-%d %H:%M:%S")
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{random.randint(1, 1000):04d}"

        title_map = {
            "refund": f"Refund request for order {order_id}",
            "address_change": f"Change shipping address for {order_id}",
            "product_inquiry": f"Product inquiry about {order_id}",
            "complaint": f"Complaint about order {order_id}",
            "general": f"General inquiry",
        }
        title = title_map[category]

        description = f"User {user_id} submitted {action} request. Category: {category}. Priority: {priority}."
        history = f'[{{"status": "created", "note": "Ticket created."}}, {{"status": "{status}", "note": "Last update."}}]'

        tickets.append((
            ticket_id, user_id, title, description, priority, category,
            action, status, order_id, created_at, updated_at, history
        ))
    return tickets


def generate_logistics(order_record: dict, logistics_id: str) -> tuple[dict, list[dict]]:
    """
    为订单生成物流主记录和轨迹记录
    
    Args:
        order_record: 订单记录，包含 order_id, status, order_date, address
        logistics_id: 物流记录ID
    
    Returns:
        (logistics_record, tracking_records)
    """
    order_id = order_record["order_id"]
    order_status = order_record["status"]
    order_date_str = order_record["order_date"]
    receiver_address = order_record["address"]

    express_name, express_code = random.choice(EXPRESS_COMPANIES)
    tracking_number = f"{express_code}{random.randint(100000000000, 999999999999)}"

    order_date = datetime.strptime(order_date_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.now()

    logistics_status = LOGISTICS_STATUS_MAP.get(order_status, "pending")

    if logistics_status == "delivered":
        deliver_date = order_date + timedelta(days=random.randint(3, 7))
        estimated_delivery = (order_date + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        delivered_at = deliver_date.strftime("%Y-%m-%d %H:%M:%S")
    elif logistics_status == "in_transit":
        days_since_order = (now - order_date).days
        if days_since_order < 2:
            estimated_delivery = (now + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            estimated_delivery = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        delivered_at = None
    else:
        estimated_delivery = (order_date + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        delivered_at = None

    created_at = order_date.strftime("%Y-%m-%d %H:%M:%S")
    updated_at = now.strftime("%Y-%m-%d %H:%M:%S")

    logistics_record = {
        "logistics_id": logistics_id,
        "order_id": order_id,
        "express_company": express_name,
        "express_company_code": express_code,
        "tracking_number": tracking_number,
        "status": logistics_status,
        "sender_address": "广东省深圳市龙华区某电商仓库",
        "receiver_address": receiver_address,
        "weight": random.randint(100, 5000),
        "fee": round(random.uniform(8, 25), 2),
        "channel": "domestic",
        "package_count": 1,
        "insure_fee": round(random.uniform(0, 10), 2),
        "signer": "本人" if logistics_status == "delivered" else None,
        "estimated_delivery": estimated_delivery,
        "delivered_at": delivered_at,
        "created_at": created_at,
        "updated_at": updated_at,
    }

    tracking_records = []
    status_flow = _get_status_flow(logistics_status)

    for idx, status in enumerate(status_flow):
        if status == "pending":
            continue

        desc_list = TRACKING_DESCRIPTIONS.get(status, ["状态更新"])
        description = random.choice(desc_list)

        location_map = {
            "picked_up": ["深圳市龙华区", "商家仓库", "深圳分拨中心"],
            "in_transit": ["广州转运中心", "途经杭州", "上海分拨中心", "北京转运中心"],
            "out_for_delivery": ["目的地区", "快递员已取出"],
            "delivered": ["收货地址", "已签收"],
            "returned": ["商家仓库", "退件处理中心"],
            "exception": ["异常处理中心", "联系收件人中"],
        }
        location = random.choice(location_map.get(status, ["某地"]))

        if status == "delivered":
            timestamp = delivered_at or estimated_delivery
        elif status == "out_for_delivery":
            timestamp = (datetime.strptime(estimated_delivery, "%Y-%m-%d %H:%M:%S") - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        elif status == "in_transit":
            timestamp = (order_date + timedelta(days=random.randint(1, 3))).strftime("%Y-%m-%d %H:%M:%S")
        elif status == "picked_up":
            timestamp = (order_date + timedelta(hours=random.randint(2, 12))).strftime("%Y-%m-%d %H:%M:%S")
        else:
            timestamp = random_date(30)

        tracking_id = f"LT-{datetime.now().strftime('%Y%m%d')}-{len(tracking_records) + 1:04d}"

        tracking_records.append({
            "tracking_id": tracking_id,
            "logistics_id": logistics_id,
            "status": status,
            "location": location,
            "description": description,
            "operator": None,
            "timestamp": timestamp,
            "created_at": timestamp,
        })

    return logistics_record, tracking_records


def _get_status_flow(final_status: str) -> list[str]:
    """根据最终状态生成状态流转链"""
    flow_map = {
        "pending": ["pending"],
        "picked_up": ["pending", "picked_up"],
        "in_transit": ["pending", "picked_up", "in_transit"],
        "out_for_delivery": ["pending", "picked_up", "in_transit", "out_for_delivery"],
        "delivered": ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered"],
        "returned": ["pending", "picked_up", "in_transit", "returned"],
        "exception": ["pending", "picked_up", "in_transit", "exception"],
    }
    return flow_map.get(final_status, ["pending"])


def init_database(db_path: str | Path = DB_PATH, drop_existing: bool = False) -> None:
    if isinstance(db_path, str):
        db_path = Path(db_path)

    if drop_existing and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            address TEXT NOT NULL,
            order_date TEXT NOT NULL,
            deliver_date TEXT,
            can_update_address INTEGER NOT NULL,
            refund_eligible INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT NOT NULL,
            category TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            order_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            history TEXT
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_pending_dedup
        ON tickets(order_id, action, status)
        WHERE status NOT IN ('resolved', 'rejected', 'closed')
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS manual_reviews (
            review_id TEXT PRIMARY KEY,
            session_id TEXT,
            user_id TEXT,
            action TEXT,
            risk_level TEXT,
            reason TEXT,
            ticket_id TEXT,
            order_id TEXT,
            workflow_snapshot TEXT,
            evidence TEXT,
            status TEXT,
            resolution TEXT,
            reviewer_note TEXT,
            created_at TEXT,
            resolved_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logistics (
            logistics_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            express_company TEXT NOT NULL,
            express_company_code TEXT,
            tracking_number TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            sender_address TEXT,
            receiver_address TEXT,
            weight INTEGER,
            fee REAL DEFAULT 0.0,
            channel TEXT DEFAULT 'domestic',
            package_count INTEGER DEFAULT 1,
            insure_fee REAL DEFAULT 0.0,
            signer TEXT,
            estimated_delivery TEXT,
            delivered_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logistics_tracking (
            tracking_id TEXT PRIMARY KEY,
            logistics_id TEXT NOT NULL,
            status TEXT NOT NULL,
            location TEXT,
            description TEXT,
            operator TEXT,
            timestamp TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (logistics_id) REFERENCES logistics(logistics_id)
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM orders")
    existing_orders = cursor.fetchone()[0]

    if existing_orders == 0:
        print(f"Seeding 1000 orders...")
        orders = generate_orders(1000)

        # Insert specific test orders for backward compatibility with tests
        test_orders = [
            (
                "ORD-20260401-0001",
                "anonymous",
                "Smart Speaker",
                299.00,
                "shipped",
                "Shanghai Pudong New Area 1",
                "2026-04-01 10:00:00",
                None,
                0,  # can_update_address = False
                1,  # refund_eligible = True
            ),
            (
                "ORD-20260402-0002",
                "anonymous",
                "Laptop Stand",
                1399.00,
                "processing",
                "Hangzhou Xihu District 88",
                "2026-04-02 14:30:00",
                None,
                1,  # can_update_address = True
                1,  # refund_eligible = True
            ),
            (
                "ORD-20260403-0003",
                "anonymous",
                "USB Dock",
                99.00,
                "delivered",
                "Suzhou Industrial Park 66",
                "2026-03-20 09:15:00",
                "2026-03-25 16:45:00",
                0,  # can_update_address = False
                0,  # refund_eligible = False (delivered > 7 days ago)
            ),
            (
                "ORD-20260404-0004",
                "anonymous",
                "Gaming Laptop",
                8999.00,
                "processing",
                "Beijing Haidian District 100",
                "2026-04-04 11:00:00",
                None,
                1,  # can_update_address = True
                1,  # refund_eligible = True
            ),
        ]
        orders.extend(test_orders)

        cursor.executemany("""
            INSERT OR IGNORE INTO orders 
            (order_id, user_id, product_name, amount, status, address, 
             order_date, deliver_date, can_update_address, refund_eligible)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, orders)

        print(f"Seeding logistics for {len(orders)} orders...")
        logistics_records = []
        tracking_records = []

        for idx, order in enumerate(orders):
            order_id = order[0]
            order_status = order[4]
            order_date_str = order[6]
            address = order[5]

            order_dict = {
                "order_id": order_id,
                "status": order_status,
                "order_date": order_date_str,
                "address": address,
            }

            if order_status not in ["cancelled", "refunded", "pending"]:
                logistics_id = f"LG-{datetime.now().strftime('%Y%m%d')}-{idx + 1:05d}"
                logistics_rec, tracking_recs = generate_logistics(order_dict, logistics_id)

                logistics_values = (
                    logistics_rec["logistics_id"],
                    logistics_rec["order_id"],
                    logistics_rec["express_company"],
                    logistics_rec["express_company_code"],
                    logistics_rec["tracking_number"],
                    logistics_rec["status"],
                    logistics_rec["sender_address"],
                    logistics_rec["receiver_address"],
                    logistics_rec["weight"],
                    logistics_rec["fee"],
                    logistics_rec["channel"],
                    logistics_rec["package_count"],
                    logistics_rec["insure_fee"],
                    logistics_rec["signer"],
                    logistics_rec["estimated_delivery"],
                    logistics_rec["delivered_at"],
                    logistics_rec["created_at"],
                    logistics_rec["updated_at"],
                )
                logistics_records.append(logistics_values)

                for tr in tracking_recs:
                    tracking_values = (
                        tr["tracking_id"],
                        tr["logistics_id"],
                        tr["status"],
                        tr["location"],
                        tr["description"],
                        tr["operator"],
                        tr["timestamp"],
                        tr["created_at"],
                    )
                    tracking_records.append(tracking_values)

        if logistics_records:
            cursor.executemany("""
                INSERT OR IGNORE INTO logistics
                (logistics_id, order_id, express_company, express_company_code, tracking_number,
                 status, sender_address, receiver_address, weight, fee, channel, package_count,
                 insure_fee, signer, estimated_delivery, delivered_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, logistics_records)

        if tracking_records:
            cursor.executemany("""
                INSERT OR IGNORE INTO logistics_tracking
                (tracking_id, logistics_id, status, location, description, operator, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, tracking_records)

        print(f"Seeding 50 tickets...")
        tickets = generate_tickets(50)
        cursor.executemany("""
            INSERT INTO tickets
            (ticket_id, user_id, title, description, priority, category,
             action, status, order_id, created_at, updated_at, history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tickets)

        conn.commit()
        print(f"Database initialized at {db_path}")
        print(f"  Orders: {len(orders)}")
        print(f"  Logistics: {len(logistics_records)}")
        print(f"  Tracking records: {len(tracking_records)}")
        print(f"  Tickets: 50")
    else:
        print(f"Database already has {existing_orders} orders. Skipping seed.")

    conn.close()


if __name__ == "__main__":
    init_database(drop_existing=True)