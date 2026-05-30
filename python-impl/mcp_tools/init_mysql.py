"""
MySQL数据库初始化脚本
迁移数据到MySQL并初始化测试数据
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

try:
    import pymysql
except ImportError:
    print("PyMySQL not installed. Run: pip install pymysql")
    exit(1)

load_dotenv()

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
]

LOGISTICS_STATUSES = ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "returned"]
LOGISTICS_STATUS_MAP = {
    "pending": "pending",
    "processing": "picked_up",
    "shipped": "in_transit",
    "delivered": "delivered",
    "cancelled": "returned",
    "refunded": "returned",
}


def get_mysql_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "smart_cs"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def random_address() -> str:
    province, districts = random.choice(CITIES)
    district = random.choice(districts)
    street_num = random.randint(1, 999)
    return f"{province}{district}{street_num}号"


def random_date(days_back: int = 90) -> str:
    return (datetime.now() - timedelta(days=random.randint(0, days_back))).strftime("%Y-%m-%d %H:%M:%S")


def init_database(drop_existing: bool = False):
    conn = get_mysql_connection()
    cursor = conn.cursor()

    print("Truncating existing data...")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in ["logistics_tracking", "logistics", "manual_reviews", "tickets", "orders", "users_auth", "users"]:
        cursor.execute(f"TRUNCATE TABLE {table}")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()

    print("Seeding 1000 orders...")
    orders = []
    for i in range(1, 1001):
        order_date = datetime.now() - timedelta(days=random.randint(0, 90))
        order_id = f"ORD-{order_date.strftime('%Y%m%d')}-{i:04d}"
        user_id = random.choice(USER_IDS)
        product_name, base_price, discount_rate = random.choice(PRODUCTS)
        final_price = round(base_price * (1 - discount_rate), 2)
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        address = random_address()
        order_date_str = order_date.strftime("%Y-%m-%d %H:%M:%S")

        deliver_date = None
        if status == "delivered":
            deliver_date = order_date + timedelta(days=random.randint(3, 7))
            deliver_date = deliver_date.strftime("%Y-%m-%d %H:%M:%S")

        can_update_address = 1 if status in ("pending", "processing") else 0
        refund_eligible = 1 if status in ("pending", "processing", "shipped") or (status == "delivered" and (datetime.now() - datetime.strptime(deliver_date, "%Y-%m-%d %H:%M:%S")).days <= 7) else 0

        orders.append((
            order_id, user_id, product_name, final_price, status, address,
            order_date_str, deliver_date, can_update_address, refund_eligible
        ))

    test_orders = [
        ("ORD-20260113-0001", "anonymous", "Smart Watch", 1247.04, "delivered", "Shanghai Minhang District 316号", "2026-01-13 14:02:03", "2026-01-18 14:02:03", 0, 0),
        ("ORD-20260206-0013", "anonymous", "Wireless Earbuds", 299.00, "processing", "Beijing Chaoyang District 88", "2026-02-06 09:30:00", None, 1, 1),
        ("ORD-20260324-0018", "anonymous", "Bluetooth Speaker", 599.00, "processing", "Guangzhou Tianhe District 200", "2026-03-24 16:45:00", None, 1, 1),
        ("ORD-20260401-0001", "anonymous", "Smart Speaker", 299.00, "shipped", "Shanghai Pudong New Area 1", "2026-04-01 10:00:00", None, 0, 1),
        ("ORD-20260402-0002", "anonymous", "Laptop Stand", 1399.00, "processing", "Hangzhou Xihu District 88", "2026-04-02 14:30:00", None, 1, 1),
        ("ORD-20260403-0003", "anonymous", "USB Dock", 99.00, "delivered", "Suzhou Industrial Park 66", "2026-03-20 09:15:00", "2026-03-25 16:45:00", 0, 0),
        ("ORD-20260404-0004", "anonymous", "Gaming Laptop", 8999.00, "processing", "Beijing Haidian District 100", "2026-04-04 11:00:00", None, 1, 1),
        ("ORD-20260130-0019", "anonymous", "Mechanical Keyboard", 899.00, "delivered", "Shenzhen Nanshan District 500", "2026-01-30 11:20:00", "2026-02-04 15:30:00", 0, 0),
    ]
    orders.extend(test_orders)

    cursor.executemany("""
        INSERT INTO orders 
        (order_id, user_id, product_name, amount, status, address, order_date, deliver_date, can_update_address, refund_eligible)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, orders)

    print(f"Inserted {len(orders)} orders")

    print("Seeding logistics...")
    cursor.execute("""
        SELECT order_id, status, order_date, address FROM orders 
        WHERE status NOT IN ('pending', 'cancelled', 'refunded')
    """)
    order_rows = cursor.fetchall()

    logistics_records = []
    tracking_records = []

    for idx, order in enumerate(order_rows):
        order_id = order["order_id"]
        order_status = order["status"]
        order_date_str = order["order_date"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(order["order_date"], "strftime") else str(order["order_date"])
        address = order["address"]

        express_name, express_code = random.choice(EXPRESS_COMPANIES)
        tracking_number = f"{express_code}{random.randint(100000000000, 999999999999)}"
        logistics_status = LOGISTICS_STATUS_MAP.get(order_status, "pending")

        order_date = datetime.strptime(order_date_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()

        if logistics_status == "delivered":
            deliver_dt = order_date + timedelta(days=random.randint(3, 7))
            estimated_delivery = (order_date + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
            delivered_at = deliver_dt.strftime("%Y-%m-%d %H:%M:%S")
        elif logistics_status in ["in_transit", "out_for_delivery"]:
            days_since = (now - order_date).days
            estimated_delivery = (now + timedelta(days=max(1, 2 - days_since))).strftime("%Y-%m-%d %H:%M:%S")
            delivered_at = None
        else:
            estimated_delivery = (order_date + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
            delivered_at = None

        created_at = order_date.strftime("%Y-%m-%d %H:%M:%S")
        updated_at = now.strftime("%Y-%m-%d %H:%M:%S")
        logistics_id = f"LG-{datetime.now().strftime('%Y%m%d')}-{idx + 1:05d}"

        logistics_records.append((
            logistics_id, order_id, express_name, express_code, tracking_number,
            logistics_status, "广东省深圳市龙华区某电商仓库", address,
            random.randint(100, 5000), round(random.uniform(8, 25), 2),
            "domestic", 1, round(random.uniform(0, 10), 2),
            "本人" if logistics_status == "delivered" else None,
            estimated_delivery, delivered_at, created_at, updated_at
        ))

        status_flow_map = {
            "picked_up": ["pending", "picked_up"],
            "in_transit": ["pending", "picked_up", "in_transit"],
            "out_for_delivery": ["pending", "picked_up", "in_transit", "out_for_delivery"],
            "delivered": ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered"],
        }

        flow = status_flow_map.get(logistics_status, ["pending"])
        location_map = {
            "picked_up": ["深圳市龙华区", "商家仓库", "深圳分拨中心"],
            "in_transit": ["广州转运中心", "途经杭州", "上海分拨中心"],
            "out_for_delivery": ["目的地区", "快递员已取出"],
            "delivered": ["收货地址"],
        }

        for t_idx, t_status in enumerate(flow):
            if t_status == "pending":
                continue

            descriptions = {
                "picked_up": ["快递员已揽收", "包裹已发出"],
                "in_transit": ["包裹运输中", "到达分拨中心"],
                "out_for_delivery": ["包裹正在派送中", "请保持电话畅通"],
                "delivered": ["包裹已签收", "签收人：本人"],
            }

            desc = random.choice(descriptions.get(t_status, ["状态更新"]))
            location = random.choice(location_map.get(t_status, ["某地"]))

            if t_status == "delivered":
                ts = delivered_at or estimated_delivery
            elif t_status == "out_for_delivery":
                ts = (datetime.strptime(estimated_delivery, "%Y-%m-%d %H:%M:%S") - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            elif t_status == "in_transit":
                ts = (order_date + timedelta(days=random.randint(1, 3))).strftime("%Y-%m-%d %H:%M:%S")
            elif t_status == "picked_up":
                ts = (order_date + timedelta(hours=random.randint(2, 12))).strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts = created_at

            tracking_records.append((
                f"LT-{datetime.now().strftime('%Y%m%d')}-{len(tracking_records) + 1:05d}",
                logistics_id, t_status, location, desc, None, ts, ts
            ))

    cursor.executemany("""
        INSERT INTO logistics 
        (logistics_id, order_id, express_company, express_company_code, tracking_number,
         status, sender_address, receiver_address, weight, fee, channel, package_count,
         insure_fee, signer, estimated_delivery, delivered_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, logistics_records)

    cursor.executemany("""
        INSERT INTO logistics_tracking
        (tracking_id, logistics_id, status, location, description, operator, timestamp, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, tracking_records)

    print(f"Inserted {len(logistics_records)} logistics and {len(tracking_records)} tracking records")

    print("Seeding 50 tickets...")
    tickets = []
    priorities = ["low", "medium", "high"]
    categories = ["refund", "address_change", "product_inquiry", "complaint", "general"]
    actions = ["refund_request", "address_update", "order_inquiry", "escalation", "general_inquiry"]
    statuses = ["created", "pending", "in_progress", "resolved", "closed"]

    for i in range(1, 51):
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
        description = f"User {user_id} submitted {action} request. Category: {category}."
        history = json.dumps([{"status": "created", "note": "Ticket created."}])

        tickets.append((
            ticket_id, user_id, title, description, priority, category,
            action, status, order_id, created_at, updated_at, history
        ))

    cursor.executemany("""
        INSERT INTO tickets
        (ticket_id, user_id, title, description, priority, category,
         action, status, order_id, created_at, updated_at, history)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, tickets)

    print(f"Inserted {len(tickets)} tickets")

    conn.commit()
    conn.close()

    print("\n=== Database initialization complete ===")
    print(f"Orders: {len(orders)}")
    print(f"Logistics: {len(logistics_records)}")
    print(f"Tracking: {len(tracking_records)}")
    print(f"Tickets: {len(tickets)}")


if __name__ == "__main__":
    init_database(drop_existing=True)
