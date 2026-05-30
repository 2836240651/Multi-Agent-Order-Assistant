"""tests/contract/test_mcp_tools.py：MCP 工具契约测试。

验证 4 个工具的 schema 和 handler 返回格式。

注意：本地 mcp/ 目录与已安装的 mcp SDK 命名冲突，
因此本测试直接调用 handler 函数 + 校验 Tool schema。
"""
from __future__ import annotations

import asyncio
import json

import pytest


@pytest.fixture
def tool_defs():
    """导入 MCP server 的工具定义和 handler。"""
    from mcp_tools.mcp_server import _TOOL_HANDLERS, list_tools
    tools = asyncio.run(list_tools())
    return tools, _TOOL_HANDLERS


# ── 工具注册测试 ────────────────────────────────────────────────

def test_mcp_has_4_tools(tool_defs):
    tools, _ = tool_defs
    assert len(tools) == 4


def test_tools_have_required_fields(tool_defs):
    tools, _ = tool_defs
    for tool in tools:
        assert tool.name
        assert tool.description
        assert tool.inputSchema
        assert "type" in tool.inputSchema
        assert "properties" in tool.inputSchema


def test_query_order_schema(tool_defs):
    tools, _ = tool_defs
    tool = next(t for t in tools if t.name == "query_order")
    assert "order_id" in tool.inputSchema["properties"]
    assert "order_id" in tool.inputSchema["required"]


def test_list_refunds_schema(tool_defs):
    tools, _ = tool_defs
    tool = next(t for t in tools if t.name == "list_refunds")
    assert len(tool.inputSchema.get("required", [])) == 0


def test_get_kb_doc_schema(tool_defs):
    tools, _ = tool_defs
    tool = next(t for t in tools if t.name == "get_kb_doc")
    assert "query" in tool.inputSchema["properties"]
    assert "query" in tool.inputSchema["required"]


def test_risk_check_schema(tool_defs):
    tools, _ = tool_defs
    tool = next(t for t in tools if t.name == "risk_check")
    props = tool.inputSchema["properties"]
    assert "amount" in props
    assert "reason" in props


# ── 工具调用测试（直接调 handler）──────────────────────────────

@pytest.mark.asyncio
async def test_query_order_returns_json(tool_defs):
    _, handlers = tool_defs
    result = await handlers["query_order"]({"order_id": "ORD-TEST-001"})
    data = json.loads(result)
    assert "found" in data


@pytest.mark.asyncio
async def test_list_refunds_returns_json(tool_defs):
    _, handlers = tool_defs
    result = await handlers["list_refunds"]({"limit": 5})
    data = json.loads(result)
    assert "count" in data
    assert "tickets" in data


@pytest.mark.asyncio
async def test_get_kb_doc_returns_json(tool_defs):
    _, handlers = tool_defs
    result = await handlers["get_kb_doc"]({"query": "退货政策"})
    data = json.loads(result)
    assert "query" in data
    assert "results" in data


@pytest.mark.asyncio
async def test_risk_check_returns_decision(tool_defs):
    _, handlers = tool_defs
    result = await handlers["risk_check"]({
        "amount": 99,
        "reason": "质量问题",
        "days_since_delivery": 3,
    })
    data = json.loads(result)
    assert "decision" in data
    assert data["decision"] in {"pass", "review", "reject", "unknown"}


def test_handler_map_has_all_4_tools(tool_defs):
    _, handlers = tool_defs
    assert set(handlers.keys()) == {"query_order", "list_refunds", "get_kb_doc", "risk_check"}


# ── Token 验证测试 ──────────────────────────────────────────────

def test_token_check_no_token_set(monkeypatch):
    """未设置 MCP_API_TOKEN 时，_check_token 不抛异常。"""
    monkeypatch.delenv("MCP_API_TOKEN", raising=False)
    from mcp_tools.mcp_server import _check_token
    _check_token({"order_id": "test"})  # 不应抛异常


def test_token_check_wrong_token(monkeypatch):
    """设置了 MCP_API_TOKEN 但传入错误 token 时，应抛 PermissionError。"""
    monkeypatch.setenv("MCP_API_TOKEN", "secret123")
    import importlib
    import mcp_tools.mcp_server as mod
    importlib.reload(mod)

    with pytest.raises(PermissionError):
        mod._check_token({"order_id": "test"})
