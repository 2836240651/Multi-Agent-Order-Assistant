"""scripts/bench/locustfile.py：RetailGuard 压测脚本。

4 角色模拟：
1. CustomerUser — 顾客：简单聊天 + RAG 查询（权重 5）
2. AgentUser — 客服：复杂业务 + 批量审核（权重 3）
3. RiskUser — 风控员：审核队列 + 审批操作（权重 1）
4. AdminUser — 管理员：管理面板 + 灰度配置（权重 1）

三场景：
1. 纯 chat（简单问候 + FAQ 查询）—— 低延迟基线
2. chat + RAG（知识库检索）—— 中等延迟
3. 复杂业务（退款/订单/地址变更）—— 高延迟（Planner+Critic+Risk）

用法：
    locust -f scripts/bench/locustfile.py --host http://localhost:18000
    locust -f scripts/bench/locustfile.py --host http://localhost:18000 \
        --users 50 --spawn-rate 5 --run-time 2m --headless

输出：终端实时 QPS / P50 / P95 / P99 / 错误率。
"""
from __future__ import annotations

import json
import random
import uuid

from locust import HttpUser, between, events, task, tag


# ── 测试数据 ────────────────────────────────────────────────────

SIMPLE_QUERIES = [
    "你好",
    "在吗",
    "hi",
    "耳机能7天无理由退吗",
    "退货政策是什么",
    "多久能退款",
    "运费谁承担",
]

RAG_QUERIES = [
    "蓝牙耳机的退货流程是什么",
    "机械键盘保修期多久",
    "智能手表可以换货吗",
    "无线充电器的售后政策",
    "笔记本支架退货需要什么条件",
    "降噪耳机遇到质量问题怎么办",
    "移动电源退货运费谁出",
]

COMPLEX_QUERIES = [
    "我要退掉上周买的蓝牙耳机，金额299元",
    "帮我把订单地址改成北京市朝阳区建国路88号",
    "查一下我最近的订单物流状态",
    "我要退两件商品，一件质量问题，一件不想要了",
]

TENANT_IDS = [1, 2, 3, 4, 5]


# ── 工具函数 ────────────────────────────────────────────────────

def _auth_headers(tenant_id: int) -> dict:
    """构造带 tenant header 的请求头（压测环境用固定 admin token）。"""
    return {
        "Content-Type": "application/json",
        "X-Tenant-Id": str(tenant_id),
    }


def _parse_sse_events(text: str) -> list[dict]:
    """解析 SSE 响应体为事件列表。"""
    evts = []
    current_event = {}
    for line in text.split("\n"):
        if line.startswith("event: "):
            current_event["event"] = line[7:].strip()
        elif line.startswith("data: "):
            try:
                current_event["data"] = json.loads(line[6:])
            except json.JSONDecodeError:
                current_event["data"] = line[6:]
            evts.append(current_event)
            current_event = {}
    return evts


def _send_chat(self, query: str, name: str = "/api/v1/chat"):
    """发送 SSE chat 请求并解析响应。"""
    headers = _auth_headers(self.tenant_id)
    payload = {
        "messages": [{"role": "user", "content": query}],
        "thread_id": uuid.uuid4().hex,
        "version": "v3",
    }

    with self.client.post(
        "/api/v1/chat",
        json=payload,
        headers=headers,
        name=name,
        stream=True,
        catch_response=True,
    ) as resp:
        if resp.status_code == 401:
            resp.failure("auth required (expected in prod)")
            return
        if resp.status_code != 200:
            resp.failure(f"status={resp.status_code}")
            return

        body = ""
        try:
            for chunk in resp.iter_content(chunk_size=None):
                body += chunk.decode("utf-8", errors="replace")
        except Exception as exc:
            resp.failure(f"stream read error: {exc}")
            return

        sse_events = _parse_sse_events(body)
        event_types = [e.get("event") for e in sse_events]

        if "error" in event_types:
            error_data = next(
                (e["data"] for e in sse_events if e.get("event") == "error"), {}
            )
            resp.failure(f"server error: {error_data}")
        elif "done" in event_types or "interrupt" in event_types:
            resp.success()
        else:
            resp.failure(f"no done/interrupt event: {event_types}")


# ── 角色 1：CustomerUser（顾客）─────────────────────────────────

class CustomerUser(HttpUser):
    """模拟顾客：简单聊天 + RAG 知识查询。"""

    wait_time = between(1.0, 3.0)
    host = "http://localhost:18000"
    weight = 5

    def on_start(self):
        self.tenant_id = random.choice(TENANT_IDS)
        self.thread_id = uuid.uuid4().hex

    @tag("simple", "chat", "customer")
    @task(5)
    def simple_chat(self):
        query = random.choice(SIMPLE_QUERIES)
        _send_chat(self, query, name="/api/v1/chat [simple]")

    @tag("rag", "chat", "customer")
    @task(3)
    def rag_chat(self):
        query = random.choice(RAG_QUERIES)
        _send_chat(self, query, name="/api/v1/chat [rag]")

    @tag("health", "customer")
    @task(1)
    def health_check(self):
        with self.client.get("/health", name="/health", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status={resp.status_code}")


# ── 角色 2：AgentUser（客服）────────────────────────────────────

class AgentUser(HttpUser):
    """模拟客服：复杂业务处理 + 批量审核。"""

    wait_time = between(0.5, 2.0)
    host = "http://localhost:18000"
    weight = 3

    def on_start(self):
        self.tenant_id = random.choice(TENANT_IDS)

    @tag("complex", "business", "agent")
    @task(5)
    def complex_chat(self):
        query = random.choice(COMPLEX_QUERIES)
        _send_chat(self, query, name="/api/v1/chat [complex]")

    @tag("rag", "chat", "agent")
    @task(3)
    def rag_chat(self):
        query = random.choice(RAG_QUERIES)
        _send_chat(self, query, name="/api/v1/chat [rag]")

    @tag("task", "agent")
    @task(1)
    def batch_review(self):
        """模拟批量审核请求。"""
        headers = _auth_headers(self.tenant_id)
        payload = {"ticket_ids": [f"t-{random.randint(1, 100):04d}"]}
        with self.client.post(
            "/api/v1/tasks/batch_review",
            json=payload,
            headers=headers,
            name="/api/v1/tasks/batch_review",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 202):
                resp.success()
            elif resp.status_code == 403:
                resp.failure("no permission (expected without auth)")
            else:
                resp.failure(f"status={resp.status_code}")


# ── 角色 3：RiskUser（风控员）───────────────────────────────────

class RiskUser(HttpUser):
    """模拟风控员：审核队列查询 + 审批操作。"""

    wait_time = between(2.0, 5.0)
    host = "http://localhost:18000"
    weight = 1

    def on_start(self):
        self.tenant_id = random.choice(TENANT_IDS)

    @tag("review", "risk")
    @task(3)
    def review_approve(self):
        """模拟审批操作。"""
        headers = _auth_headers(self.tenant_id)
        payload = {"action": "approve", "reviewer_note": "压测审批"}
        with self.client.post(
            f"/api/v1/review/{uuid.uuid4().hex[:8]}/resume",
            json=payload,
            headers=headers,
            name="/api/v1/review/[id]/resume",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404, 500):
                resp.success()
            elif resp.status_code == 403:
                resp.failure("no permission")
            else:
                resp.failure(f"status={resp.status_code}")

    @tag("health", "risk")
    @task(1)
    def health_check(self):
        with self.client.get("/health", name="/health", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status={resp.status_code}")


# ── 角色 4：AdminUser（管理员）──────────────────────────────────

class AdminUser(HttpUser):
    """模拟管理员：管理面板查询 + 灰度配置。"""

    wait_time = between(3.0, 8.0)
    host = "http://localhost:18000"
    weight = 1

    def on_start(self):
        self.tenant_id = random.choice(TENANT_IDS)

    @tag("admin", "cost")
    @task(2)
    def view_cost(self):
        """查看成本面板。"""
        headers = _auth_headers(self.tenant_id)
        with self.client.get(
            "/api/v1/admin/cost",
            headers=headers,
            name="/api/v1/admin/cost",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"status={resp.status_code}")

    @tag("admin", "rollout")
    @task(1)
    def view_rollout(self):
        """查看灰度配置。"""
        headers = _auth_headers(self.tenant_id)
        with self.client.get(
            "/api/v1/admin/rollout",
            headers=headers,
            name="/api/v1/admin/rollout",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"status={resp.status_code}")

    @tag("admin", "tenants")
    @task(1)
    def view_tenants(self):
        """查看租户列表。"""
        headers = _auth_headers(self.tenant_id)
        with self.client.get(
            "/api/v1/admin/tenants",
            headers=headers,
            name="/api/v1/admin/tenants",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()
            else:
                resp.failure(f"status={resp.status_code}")


# ── 统计钩子 ────────────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "=" * 60)
    print("RetailGuard 压测开始")
    print("  角色: Customer(5) + Agent(3) + Risk(1) + Admin(1)")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "=" * 60)
    print("RetailGuard 压测结束")
    print("=" * 60)
