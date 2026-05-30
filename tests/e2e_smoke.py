"""
RetailGuard Copilot — Playwright E2E 自动化验证脚本

覆盖 20 项功能需求的联调节点：
  - API 层：登录/鉴权/CRUD/权限
  - UI 层：页面加载/导航/表单交互

用法：
    python tests/e2e_smoke.py
    python tests/e2e_smoke.py --headed  # 有头模式（可视化）
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass

# ── 配置 ─────────────────────────────────────────────────────
BACKEND = "http://localhost:18001"
FRONTEND = "http://localhost:5173"

DEMO_USERS = {
    "admin":   {"username": "admin_a",   "password": "123456", "tenant_id": 1},
    "agent":   {"username": "agent_a",   "password": "123456", "tenant_id": 1},
    "risk":    {"username": "risk_a",    "password": "123456", "tenant_id": 1},
    "customer":{"username": "customer_a","password": "123456", "tenant_id": 1},
}


# ── 测试结果收集 ──────────────────────────────────────────────
@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0


results: list[TestResult] = []


def record(name: str, passed: bool, detail: str = "", duration_ms: float = 0):
    results.append(TestResult(name, passed, detail, duration_ms))
    icon = "[PASS]" if passed else "[FAIL]"
    print(f"  {icon} {name}" + (f" -- {detail}" if detail else ""))


# ── API 层测试（用 requests）─────────────────────────────────────
def test_api():
    import requests as req

    print("\n--- API Layer Tests ---")

    # T01: 健康检查
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/health", timeout=5)
        record("T01 GET /health", r.status_code == 200 and r.json().get("status") == "ok",
               f"status={r.status_code}", (time.time()-t0)*1000)
    except Exception as e:
        record("T01 GET /health", False, str(e))

    # T02: 无 token 访问 → 401
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/orders", timeout=5)
        record("T02 no token -> 401", r.status_code == 401,
               f"status={r.status_code}", (time.time()-t0)*1000)
    except Exception as e:
        record("T02 no token -> 401", False, str(e))

    # T03: 错误密码 → 401
    t0 = time.time()
    try:
        r = req.post(f"{BACKEND}/auth/login", json={
            "username": "admin_a", "password": "wrong", "tenant_id": 1
        }, timeout=5)
        record("T03 wrong password -> rejected", r.status_code in (401, 403, 422, 500),
               f"status={r.status_code}", (time.time()-t0)*1000)
    except Exception as e:
        record("T03 wrong password -> rejected", False, str(e))

    # T04: admin 登录成功
    token = None
    t0 = time.time()
    try:
        r = req.post(f"{BACKEND}/auth/login", json=DEMO_USERS["admin"], timeout=5)
        data = r.json()
        token = data.get("access_token")
        ok = r.status_code == 200 and token and data.get("user", {}).get("username") == "admin_a"
        record("T04 admin login -> JWT", ok,
               f"user={data.get('user',{}).get('display_name','?')}", (time.time()-t0)*1000)
    except Exception as e:
        record("T04 admin login -> JWT", False, str(e))

    if not token:
        print("  [WARN] No token, skipping remaining API tests")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # T05: GET /auth/me
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/auth/me", headers=headers, timeout=5)
        data = r.json()
        record("T05 GET /auth/me", r.status_code == 200 and "roles" in data,
               f"roles={data.get('roles')}", (time.time()-t0)*1000)
    except Exception as e:
        record("T05 GET /auth/me", False, str(e))

    # T06: GET /api/v1/orders
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/orders", headers=headers, timeout=5)
        data = r.json()
        record("T06 GET /api/v1/orders", r.status_code == 200 and "orders" in data,
               f"total={data.get('total',0)}", (time.time()-t0)*1000)
    except Exception as e:
        record("T06 GET /api/v1/orders", False, str(e))

    # T07: GET /api/v1/tickets
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/tickets", headers=headers, timeout=5)
        data = r.json()
        record("T07 GET /api/v1/tickets", r.status_code == 200 and "tickets" in data,
               f"total={data.get('total',0)}", (time.time()-t0)*1000)
    except Exception as e:
        record("T07 GET /api/v1/tickets", False, str(e))

    # T08: GET /api/v1/refunds
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/refunds", headers=headers, timeout=5)
        data = r.json()
        record("T08 GET /api/v1/refunds", r.status_code == 200 and "refunds" in data,
               f"total={data.get('total',0)}", (time.time()-t0)*1000)
    except Exception as e:
        record("T08 GET /api/v1/refunds", False, str(e))

    # T09: GET /api/v1/threads
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/threads", headers=headers, timeout=5)
        data = r.json()
        record("T09 GET /api/v1/threads", r.status_code == 200 and "threads" in data,
               f"count={len(data.get('threads',[]))}", (time.time()-t0)*1000)
    except Exception as e:
        record("T09 GET /api/v1/threads", False, str(e))

    # T10: GET /api/v1/review/queue
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/review/queue", headers=headers, timeout=5)
        data = r.json()
        record("T10 GET /api/v1/review/queue", r.status_code == 200 and "tickets" in data,
               f"total={data.get('total',0)}", (time.time()-t0)*1000)
    except Exception as e:
        record("T10 GET /api/v1/review/queue", False, str(e))

    # T11: GET /api/v1/admin/cost
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/admin/cost", headers=headers, timeout=5)
        record("T11 GET /api/v1/admin/cost", r.status_code == 200,
               f"status={r.status_code}", (time.time()-t0)*1000)
    except Exception as e:
        record("T11 GET /api/v1/admin/cost", False, str(e))

    # T12: GET /api/v1/admin/tenants
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/admin/tenants", headers=headers, timeout=5)
        data = r.json()
        record("T12 GET /api/v1/admin/tenants", r.status_code == 200 and len(data.get("tenants",[])) == 5,
               f"tenants={len(data.get('tenants',[]))}", (time.time()-t0)*1000)
    except Exception as e:
        record("T12 GET /api/v1/admin/tenants", False, str(e))

    # T13: GET /api/v1/admin/rollout
    t0 = time.time()
    try:
        r = req.get(f"{BACKEND}/api/v1/admin/rollout", headers=headers, timeout=5)
        data = r.json()
        record("T13 GET /api/v1/admin/rollout", r.status_code == 200 and "weights" in data,
               f"weights={data.get('weights')}", (time.time()-t0)*1000)
    except Exception as e:
        record("T13 GET /api/v1/admin/rollout", False, str(e))

    # T14: 多角色登录
    for role, creds in DEMO_USERS.items():
        t0 = time.time()
        try:
            r = req.post(f"{BACKEND}/auth/login", json=creds, timeout=5)
            ok = r.status_code == 200 and r.json().get("access_token")
            record(f"T14 {role} 角色登录", ok, f"status={r.status_code}", (time.time()-t0)*1000)
        except Exception as e:
            record(f"T14 {role} 角色登录", False, str(e))

    # T15: customer 无权访问 admin 端点
    t0 = time.time()
    try:
        r_cust = req.post(f"{BACKEND}/auth/login", json=DEMO_USERS["customer"], timeout=5)
        cust_token = r_cust.json().get("access_token", "")
        cust_h = {"Authorization": f"Bearer {cust_token}"}
        r2 = req.get(f"{BACKEND}/api/v1/admin/tenants", headers=cust_h, timeout=5)
        record("T15 customer → admin API → 403", r2.status_code == 403,
               f"status={r2.status_code}", (time.time()-t0)*1000)
    except Exception as e:
        record("T15 customer → admin API → 403", False, str(e))


# ── UI 层测试（Playwright）───────────────────────────────────────
def test_ui(headed: bool = False):
    from playwright.sync_api import sync_playwright

    print("\n--- UI Layer Tests (Playwright) ---")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context()
        page = context.new_page()

        # U01: 前端首页加载
        t0 = time.time()
        try:
            page.goto(FRONTEND, timeout=10000)
            title = page.title()
            has_login = page.locator("input[type=password]").count() > 0 or \
                        page.locator("text=登录").count() > 0 or \
                        page.locator("text=Login").count() > 0
            record("U01 homepage -> login page", has_login,
                   f"title='{title}'", (time.time()-t0)*1000)
        except Exception as e:
            record("U01 homepage -> login page", False, str(e))

        # U02: admin 登录流程
        t0 = time.time()
        try:
            page.goto(f"{FRONTEND}/login", timeout=10000)
            page.wait_for_timeout(1000)

            # 找用户名/密码输入框
            username_input = page.locator("input[type=text]").first
            password_input = page.locator("input[type=password]").first

            username_input.fill("admin_a")
            password_input.fill("123456")

            # 点击登录按钮
            login_btn = page.locator("button:has-text('登录'), button:has-text('Login'), button[type=submit]").first
            login_btn.click()

            # 等待跳转（登录成功后应跳转到 /admin/dashboard 或 /chat）
            page.wait_for_timeout(3000)
            current_url = page.url
            logged_in = "/login" not in current_url
            record("U02 admin login -> redirect", logged_in,
                   f"url={current_url}", (time.time()-t0)*1000)
        except Exception as e:
            record("U02 admin login -> redirect", False, str(e))

        # U03: 侧边栏导航可见
        t0 = time.time()
        try:
            sidebar = page.locator("aside, .sidebar, nav")
            has_sidebar = sidebar.count() > 0
            record("U03 sidebar navigation", has_sidebar,
                   f"count={sidebar.count()}", (time.time()-t0)*1000)
        except Exception as e:
            record("U03 sidebar navigation", False, str(e))

        # U04~U10: 各角色页面导航测试
        admin_pages = [
            ("U04", "/admin/dashboard", "管理员仪表板"),
            ("U05", "/admin/rollout", "灰度管理"),
            ("U06", "/admin/tenants", "租户管理"),
            ("U07", "/admin/cost", "成本面板"),
            ("U08", "/admin/traces", "Trace"),
            ("U09", "/risk/reviews", "风控审核"),
            ("U10", "/agent/dashboard", "客服工作台"),
        ]

        for uid, path, _ in admin_pages:
            t0 = time.time()
            try:
                page.goto(f"{FRONTEND}{path}", timeout=10000)
                page.wait_for_timeout(1500)
                # 检查页面有内容（不是空白/不是跳转到 login）
                not_login = "/login" not in page.url
                body_text = page.locator("body").inner_text()
                has_content = len(body_text.strip()) > 50
                record(f"{uid} 导航 {path}", not_login and has_content,
                       f"url={page.url}", (time.time()-t0)*1000)
            except Exception as e:
                record(f"{uid} 导航 {path}", False, str(e))

        # U11: order list page
        t0 = time.time()
        try:
            page.goto(f"{FRONTEND}/orders", timeout=10000)
            page.wait_for_timeout(2000)
            not_login = "/login" not in page.url
            has_content = len(page.locator("body").inner_text().strip()) > 30
            record("U11 order list page", not_login and has_content,
                   f"url={page.url}", (time.time()-t0)*1000)
        except Exception as e:
            record("U11 order list page", False, str(e))

        # U12: refund form page
        t0 = time.time()
        try:
            page.goto(f"{FRONTEND}/refund", timeout=10000)
            page.wait_for_timeout(2000)
            not_login = "/login" not in page.url
            has_content = len(page.locator("body").inner_text().strip()) > 30
            record("U12 refund form page", not_login and has_content,
                   f"url={page.url}", (time.time()-t0)*1000)
        except Exception as e:
            record("U12 refund form page", False, str(e))

        # U13: address change page
        t0 = time.time()
        try:
            page.goto(f"{FRONTEND}/address-change", timeout=10000)
            page.wait_for_timeout(2000)
            not_login = "/login" not in page.url
            has_content = len(page.locator("body").inner_text().strip()) > 30
            record("U13 address change page", not_login and has_content,
                   f"url={page.url}", (time.time()-t0)*1000)
        except Exception as e:
            record("U13 address change page", False, str(e))

        # U14: session inbox page
        t0 = time.time()
        try:
            page.goto(f"{FRONTEND}/agent/sessions", timeout=10000)
            page.wait_for_timeout(2000)
            not_login = "/login" not in page.url
            has_content = len(page.locator("body").inner_text().strip()) > 30
            record("U14 session inbox page", not_login and has_content,
                   f"url={page.url}", (time.time()-t0)*1000)
        except Exception as e:
            record("U14 session inbox page", False, str(e))

        # U15: 聊天页
        t0 = time.time()
        try:
            page.goto(f"{FRONTEND}/chat", timeout=10000)
            page.wait_for_timeout(1500)
            has_chat = page.locator("textarea, input[placeholder*=输入], input[placeholder*=问题]").count() > 0
            record("U15 chat page (input)", has_chat,
                   f"url={page.url}", (time.time()-t0)*1000)
        except Exception as e:
            record("U15 chat page (input)", False, str(e))

        browser.close()


# ── 汇总 ────────────────────────────────────────────────────────
def print_summary():
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {passed}/{total} passed" + (f", {failed} failed" if failed else ""))
    print(f"{'='*60}")

    if failed:
        print("\n  Failed items:")
        for r in results:
            if not r.passed:
                print(f"    [FAIL] {r.name} -- {r.detail}")

    avg_ms = sum(r.duration_ms for r in results) / total if total else 0
    print(f"\n  Avg response: {avg_ms:.0f}ms")
    print()

    return 0 if failed == 0 else 1


# ── 入口 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    headed = "--headed" in sys.argv
    print("=" * 56)
    print("  RetailGuard Copilot -- E2E Smoke Test")
    print("=" * 56)
    print(f"  Backend: {BACKEND}")
    print(f"  Frontend: {FRONTEND}")

    test_api()
    test_ui(headed)

    sys.exit(print_summary())
