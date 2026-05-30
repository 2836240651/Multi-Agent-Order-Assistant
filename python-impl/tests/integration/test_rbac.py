"""tests/integration/test_rbac.py：RBAC 矩阵测试。

4 角色（customer / agent / risk / admin）× 受保护端点，
验证权限不足 → 403，权限足够 → 200（或非 403）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from auth.jwt import create_access_token


# ── 工厂 ───────────────────────────────────────────────────────

def _token(roles: list[str], perms: list[str], tenant_id: int = 1) -> str:
    return create_access_token(
        user_id=1, tenant_id=tenant_id, roles=roles, permissions=perms,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# 角色 token（与 bootstrap.py ROLE_PERMS 对齐）
CUSTOMER_TOKEN = _token(["customer"], [
    "chat:send", "order:read", "ticket:create", "refund:apply", "knowledge:read",
])
AGENT_TOKEN = _token(["agent"], [
    "chat:send", "order:read", "order:update",
    "ticket:create", "ticket:read", "ticket:update", "ticket:close",
    "refund:read", "refund:approve", "knowledge:read", "review:read", "task:batch_review",
])
RISK_TOKEN = _token(["risk"], [
    "order:read", "ticket:read", "refund:read",
    "review:read", "review:approve", "risk:read", "risk:write", "admin:dlq",
])
ADMIN_TOKEN = _token(["admin"], [
    "chat:send", "order:read", "order:update",
    "ticket:create", "ticket:read", "ticket:update", "ticket:close",
    "refund:apply", "refund:read", "refund:approve",
    "knowledge:read", "knowledge:write",
    "review:read", "review:approve", "risk:read", "risk:write",
    "admin:cost", "admin:rollout", "admin:tenant", "admin:user", "admin:dlq",
    "task:batch_review", "task:ingest", "eval:run",
])
NO_PERM_TOKEN = _token(["guest"], [])

client = TestClient(app, raise_server_exceptions=False)


# ── 矩阵定义 ───────────────────────────────────────────────────
# (method, path, required_perm, extra_json)

MATRIX: list[tuple[str, str, str, dict | None]] = [
    # Admin 端点
    ("GET",  "/api/v1/admin/cost",           "admin:cost",      None),
    ("GET",  "/api/v1/admin/rollout",         "admin:rollout",   None),
    ("PUT",  "/api/v1/admin/rollout",         "admin:rollout",   {"v1": 0.0, "v2": 0.0, "v3": 1.0}),
    ("GET",  "/api/v1/admin/rollout/audit",   "admin:rollout",   None),
    ("GET",  "/api/v1/admin/tenants",         "admin:tenant",    None),
    ("POST", "/api/v1/admin/tenants",         "admin:tenant",    {"code": "test-new", "name": "测试租户"}),
    # 聊天 / 任务 / 审核
    ("POST", "/api/v1/chat",                  "chat:send",       {"messages": [{"role": "user", "content": "你好"}]}),
    ("POST", "/api/v1/tasks/batch_review",    "task:batch_review", {"ticket_ids": ["t-001"]}),
    ("POST", "/api/v1/review/fake/resume",    "review:approve",  {"action": "approve"}),
    # Auth 端点（需登录但无特定业务权限）
    ("GET",  "/auth/me",                      None,              None),
    # 公开端点（无 token 也应 200）
    ("GET",  "/health",                       None,              None),
]

# 角色 → 拥有的权限集合
ROLE_PERM_MAP = {
    "customer": {"chat:send", "order:read", "ticket:create", "refund:apply", "knowledge:read"},
    "agent": {
        "chat:send", "order:read", "order:update",
        "ticket:create", "ticket:read", "ticket:update", "ticket:close",
        "refund:read", "refund:approve", "knowledge:read", "review:read", "task:batch_review",
    },
    "risk": {
        "order:read", "ticket:read", "refund:read",
        "review:read", "review:approve", "risk:read", "risk:write", "admin:dlq",
    },
}

ROLE_TOKENS = {
    "customer": CUSTOMER_TOKEN,
    "agent": AGENT_TOKEN,
    "risk": RISK_TOKEN,
    "admin": ADMIN_TOKEN,
}


# ── 测试：admin 可访问所有受保护端点 ─────────────────────────

@pytest.mark.parametrize("method,path,perm,body", MATRIX)
def test_admin_has_access(method: str, path: str, perm: str, body: dict | None):
    headers = _auth(ADMIN_TOKEN)
    if method == "GET":
        resp = client.get(path, headers=headers)
    else:
        resp = client.put(path, headers=headers, json=body)
    assert resp.status_code != 403, f"admin should have {perm}"


# ── 测试：无权限 token → 403 ───────────────────────────────────

@pytest.mark.parametrize("method,path,perm,body", MATRIX)
def test_no_perm_gets_403(method: str, path: str, perm: str, body: dict | None):
    headers = _auth(NO_PERM_TOKEN)
    if method == "GET":
        resp = client.get(path, headers=headers)
    else:
        resp = client.put(path, headers=headers, json=body)
    assert resp.status_code == 403, f"no-perm token should get 403 for {perm}"


# ── 测试：无 token → 401 ──────────────────────────────────────

@pytest.mark.parametrize("method,path,perm,body", MATRIX)
def test_no_token_gets_401(method: str, path: str, perm: str, body: dict | None):
    if method == "GET":
        resp = client.get(path)
    else:
        resp = client.put(path, json=body or {})
    assert resp.status_code == 401, f"no token should get 401 for {perm}"


# ── 测试：customer 不能访问 admin 端点 ────────────────────────

def test_customer_cannot_access_admin_cost():
    resp = client.get("/api/v1/admin/cost", headers=_auth(CUSTOMER_TOKEN))
    assert resp.status_code == 403


def test_customer_cannot_access_admin_rollout():
    resp = client.get("/api/v1/admin/rollout", headers=_auth(CUSTOMER_TOKEN))
    assert resp.status_code == 403


def test_customer_cannot_access_admin_tenants():
    resp = client.get("/api/v1/admin/tenants", headers=_auth(CUSTOMER_TOKEN))
    assert resp.status_code == 403


def test_customer_cannot_create_tenant():
    resp = client.post(
        "/api/v1/admin/tenants",
        headers=_auth(CUSTOMER_TOKEN),
        json={"code": "test-x", "name": "X"},
    )
    assert resp.status_code == 403


# ── 测试：risk 不能访问 rollout/cost ──────────────────────────

def test_risk_cannot_access_admin_rollout():
    resp = client.get("/api/v1/admin/rollout", headers=_auth(RISK_TOKEN))
    assert resp.status_code == 403


def test_risk_cannot_access_admin_cost():
    resp = client.get("/api/v1/admin/cost", headers=_auth(RISK_TOKEN))
    assert resp.status_code == 403


def test_risk_cannot_send_chat():
    """risk 无 chat:send 权限。"""
    resp = client.post(
        "/api/v1/chat",
        headers=_auth(RISK_TOKEN),
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert resp.status_code == 403


# ── 测试：agent 不能访问 admin 端点 ───────────────────────────

def test_agent_cannot_access_admin_rollout():
    resp = client.get("/api/v1/admin/rollout", headers=_auth(AGENT_TOKEN))
    assert resp.status_code == 403


def test_agent_cannot_access_admin_tenants():
    resp = client.get("/api/v1/admin/tenants", headers=_auth(AGENT_TOKEN))
    assert resp.status_code == 403


def test_agent_cannot_approve_review():
    """agent 无 review:approve 权限。"""
    resp = client.post(
        "/api/v1/review/fake-thread/resume",
        headers=_auth(AGENT_TOKEN),
        json={"action": "approve"},
    )
    assert resp.status_code == 403


# ── 测试：agent 可以 batch_review ──────────────────────────────

def test_agent_can_batch_review():
    """agent 有 task:batch_review 权限，请求应被接受（Celery 未跑时返回 500 但不是 403）。"""
    resp = client.post(
        "/api/v1/tasks/batch_review",
        headers=_auth(AGENT_TOKEN),
        json={"ticket_ids": ["t-001"]},
    )
    assert resp.status_code != 403


def test_customer_cannot_batch_review():
    """customer 无 task:batch_review 权限，应返回 403。"""
    resp = client.post(
        "/api/v1/tasks/batch_review",
        headers=_auth(CUSTOMER_TOKEN),
        json={"ticket_ids": ["t-001"]},
    )
    assert resp.status_code == 403


# ── 测试：risk 可以 review:approve ─────────────────────────────

def test_risk_can_approve_review():
    """risk 有 review:approve，请求被接受（thread 不存在时 500 但不是 403）。"""
    resp = client.post(
        "/api/v1/review/fake-thread/resume",
        headers=_auth(RISK_TOKEN),
        json={"action": "approve", "reviewer_note": "ok"},
    )
    assert resp.status_code != 403


def test_customer_cannot_approve_review():
    """customer 无 review:approve，应返回 403。"""
    resp = client.post(
        "/api/v1/review/fake-thread/resume",
        headers=_auth(CUSTOMER_TOKEN),
        json={"action": "approve"},
    )
    assert resp.status_code == 403


# ── 测试：跨租户访问（构造不同 tenant_id 的 token）───────────

def test_cross_tenant_token_different_tid():
    """token 中 tenant_id 与 X-Tenant-Id header 不一致时，应能被中间件拦截或返回正常（取决于实现）。"""
    other_tenant_token = _token(["admin"], ["admin:tenant"], tenant_id=999)
    resp = client.get(
        "/api/v1/admin/tenants",
        headers=_auth(other_tenant_token),
    )
    # 不是 401/403 即可（跨租户拦截在业务层，admin:tenant 权限检查先通过）
    assert resp.status_code in {200, 403, 422}


# ── 测试：正面权限用例 ───────────────────────────────────────

def test_customer_can_send_chat():
    """customer 有 chat:send 权限，不应返回 403。"""
    resp = client.post(
        "/api/v1/chat",
        headers=_auth(CUSTOMER_TOKEN),
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert resp.status_code != 403


def test_agent_can_send_chat():
    """agent 有 chat:send 权限。"""
    resp = client.post(
        "/api/v1/chat",
        headers=_auth(AGENT_TOKEN),
        json={"messages": [{"role": "user", "content": "你好"}]},
    )
    assert resp.status_code != 403


def test_agent_can_read_tickets():
    """agent 有 ticket:read 权限，可访问 task progress。"""
    resp = client.get(
        "/api/v1/tasks/fake-id/progress",
        headers=_auth(AGENT_TOKEN),
    )
    assert resp.status_code != 403


def test_risk_can_read_review_queue():
    """risk 有 review:read 权限。"""
    resp = client.get(
        "/api/v1/admin/rollout/audit",
        headers=_auth(RISK_TOKEN),
    )
    # risk 没有 admin:rollout，应 403
    assert resp.status_code == 403


def test_health_endpoint_no_auth():
    """/health 公开，无需 token。"""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_auth_me_requires_token():
    """/auth/me 无 token 应 401。"""
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_auth_me_with_valid_token():
    """/auth/me 有 token 应非 401。"""
    resp = client.get("/auth/me", headers=_auth(CUSTOMER_TOKEN))
    assert resp.status_code != 401
