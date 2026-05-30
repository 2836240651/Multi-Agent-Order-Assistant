#!/usr/bin/env python3
"""對已部署 RetailGuard 實例做 API 聯調（無 Playwright）。

用法:
    python scripts/remote_integration.py
    python scripts/remote_integration.py --base http://8.130.73.76:10180
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass

DEFAULT_BASE = "http://8.130.73.76:10180"

USERS = {
    "customer": {"username": "customer_a", "password": "123456", "tenant_id": 1},
    "agent": {"username": "agent_a", "password": "123456", "tenant_id": 1},
    "risk": {"username": "risk_a", "password": "123456", "tenant_id": 1},
    "admin": {"username": "admin_a", "password": "123456", "tenant_id": 1},
}


@dataclass
class Row:
    name: str
    ok: bool
    detail: str = ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE, help="前端入口（nginx 反代 API）")
    parser.add_argument("--chat-timeout", type=int, default=90, help="SSE 讀取秒數")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    try:
        import requests
    except ImportError:
        print("需要 requests: pip install requests", file=sys.stderr)
        return 2

    rows: list[Row] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        rows.append(Row(name, cond, detail))
        tag = "PASS" if cond else "FAIL"
        print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))

    print(f"\n=== RetailGuard 遠端聯調 ===\nBase: {base}\n")

    # T01 health
    try:
        r = requests.get(f"{base}/health", timeout=15)
        ok("health", r.status_code == 200 and r.json().get("status") == "ok", str(r.status_code))
    except Exception as e:
        ok("health", False, str(e))

    tokens: dict[str, str] = {}
    for role, cred in USERS.items():
        try:
            r = requests.post(
                f"{base}/auth/login",
                json=cred,
                timeout=20,
            )
            if r.status_code != 200:
                ok(f"login:{role}", False, f"HTTP {r.status_code} {r.text[:120]}")
                continue
            data = r.json()
            tok = data.get("access_token") or data.get("accessToken")
            tokens[role] = tok
            ok(f"login:{role}", bool(tok), f"user={data.get('user', {}).get('username', cred['username'])}")
        except Exception as e:
            ok(f"login:{role}", False, str(e))

    if not tokens.get("customer"):
        _summary(rows)
        return 1

    cust_headers = {
        "Authorization": f"Bearer {tokens['customer']}",
        "X-Tenant-Id": "1",
    }

    # T03 /auth/me
    try:
        r = requests.get(f"{base}/auth/me", headers=cust_headers, timeout=15)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok("/auth/me", r.status_code == 200 and "customer" in (body.get("roles") or []), str(body.get("roles")))
    except Exception as e:
        ok("/auth/me", False, str(e))

    # T04 orders (customer)
    try:
        r = requests.get(f"{base}/api/v1/orders", headers=cust_headers, timeout=20)
        ok("GET /api/v1/orders", r.status_code == 200, f"count={len(r.json()) if r.ok else r.text[:80]}")
    except Exception as e:
        ok("GET /api/v1/orders", False, str(e))

    # T05 chat SSE
    try:
        r = requests.post(
            f"{base}/api/v1/chat",
            headers={**cust_headers, "Accept": "text/event-stream"},
            json={
                "messages": [{"role": "user", "content": "耳机能 7 天无理由退货吗？"}],
                "version": "v3",
            },
            stream=True,
            timeout=(10, args.chat_timeout),
        )
        if r.status_code != 200:
            ok("POST /api/v1/chat (SSE)", False, f"HTTP {r.status_code} {r.text[:200]}")
        else:
            buf = ""
            events: list[str] = []
            t0 = time.time()
            for chunk in r.iter_content(chunk_size=None):
                if chunk:
                    buf += chunk.decode("utf-8", errors="replace")
                if "event:" in buf and "\n\n" in buf:
                    for part in buf.split("\n\n"):
                        if part.strip().startswith("event:"):
                            ev = part.split("\n")[0].replace("event:", "").strip()
                            if ev and ev not in events:
                                events.append(ev)
                if "event: done" in buf or "event: error" in buf:
                    break
                if time.time() - t0 > args.chat_timeout:
                    break
            has_token = "event: token" in buf or "data:" in buf
            ok(
                "POST /api/v1/chat (SSE)",
                has_token or "event: done" in buf,
                f"events={events[:8]} len={len(buf)}",
            )
    except Exception as e:
        ok("POST /api/v1/chat (SSE)", False, str(e))

    if tokens.get("risk"):
        rh = {"Authorization": f"Bearer {tokens['risk']}", "X-Tenant-Id": "1"}
        try:
            r = requests.get(f"{base}/api/v1/review/queue", headers=rh, timeout=20)
            ok("GET /api/v1/review/queue", r.status_code == 200, f"status={r.status_code}")
        except Exception as e:
            ok("GET /api/v1/review/queue", False, str(e))

    if tokens.get("admin"):
        ah = {"Authorization": f"Bearer {tokens['admin']}", "X-Tenant-Id": "1"}
        for path in ("/api/v1/admin/cost", "/api/v1/admin/capabilities", "/api/v1/admin/rollout"):
            try:
                r = requests.get(f"{base}{path}", headers=ah, timeout=20)
                ok(f"GET {path}", r.status_code == 200, str(r.status_code))
            except Exception as e:
                ok(f"GET {path}", False, str(e))

    return _summary(rows)


def _summary(rows: list[Row]) -> int:
    passed = sum(1 for r in rows if r.ok)
    total = len(rows)
    print(f"\n--- 結果 {passed}/{total} 通過 ---\n")
    failed = [r for r in rows if not r.ok]
    if failed:
        for r in failed:
            print(f"  ✗ {r.name}: {r.detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
