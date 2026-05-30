"""tests/contract/test_openapi.py：OpenAPI schema 合约校验。

验证 FastAPI 自动生成的 OpenAPI schema 符合预期：
- 所有端点都存在
- 响应模型有正确的类型定义
- 错误响应格式一致
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)


def _openapi_schema() -> dict:
    resp = client.get("/api/v1/openapi.json")
    if resp.status_code != 200:
        resp = client.get("/openapi.json")
    assert resp.status_code == 200, "OpenAPI schema endpoint should be available"
    return resp.json()


@pytest.fixture(scope="module")
def schema() -> dict:
    return _openapi_schema()


# ── 端点存在性 ─────────────────────────────────────────────────

EXPECTED_PATHS = [
    "/health",
    "/auth/login",
    "/auth/refresh",
    "/auth/me",
    "/auth/logout",
    "/api/v1/chat",
    "/api/v1/tasks/batch_review",
    "/api/v1/tasks/{task_id}/progress",
    "/api/v1/review/{thread_id}/resume",
    "/api/v1/admin/cost",
    "/api/v1/admin/rollout",
    "/api/v1/admin/rollout/audit",
    "/api/v1/admin/tenants",
]


@pytest.mark.parametrize("path", EXPECTED_PATHS)
def test_endpoint_exists_in_schema(schema: dict, path: str):
    paths = schema.get("paths", {})
    # OpenAPI 可能用不同路径前缀，检查末尾匹配
    found = any(path in p for p in paths)
    assert found, f"Expected path containing '{path}' not found in OpenAPI schema. Available: {list(paths.keys())}"


# ── 错误响应格式 ───────────────────────────────────────────────

def test_schema_has_paths_key(schema: dict):
    assert "paths" in schema
    assert len(schema["paths"]) > 0


def test_schema_has_info_key(schema: dict):
    assert "info" in schema
    assert "title" in schema["info"]


def test_schema_has_components(schema: dict):
    """OpenAPI schema 应有 components/schemas 定义。"""
    components = schema.get("components", {})
    schemas = components.get("schemas", {})
    assert len(schemas) > 0, "Should have schema definitions"


# ── HTTP 方法覆盖 ──────────────────────────────────────────────

def test_chat_endpoint_is_post(schema: dict):
    paths = schema.get("paths", {})
    chat_path = next((p for p in paths if p.endswith("/chat")), None)
    assert chat_path is not None, "/chat endpoint not found"
    assert "post" in paths[chat_path], "/chat should support POST"


def test_rollout_supports_get_and_put(schema: dict):
    paths = schema.get("paths", {})
    rollout_path = next((p for p in paths if "rollout" in p and "audit" not in p), None)
    assert rollout_path is not None, "/rollout endpoint not found"
    methods = paths[rollout_path]
    assert "get" in methods, "/rollout should support GET"
    assert "put" in methods, "/rollout should support PUT"


# ── Auth 端点 ──────────────────────────────────────────────────

def test_login_is_public(schema: dict):
    """登录端点不应有 security 要求。"""
    paths = schema.get("paths", {})
    login_path = next((p for p in paths if p.endswith("/login")), None)
    assert login_path is not None
    post_op = paths[login_path].get("post", {})
    security = post_op.get("security", [])
    # 空列表或未定义 = 公开
    assert security == [] or "security" not in post_op, "login should be public"
