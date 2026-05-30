"""mcp_tools/mcp_server.py：MCP stdio 服务器（官方 mcp SDK）。

暴露 4 个工具供 Claude Desktop / 任��� MCP 客户端调用：
- query_order：查询订单详情
- list_refunds：列出退款工单
- get_kb_doc：查询知识库文档
- risk_check：风控评分

启动方式：
    python -m mcp_tools.mcp_server                  # stdio 模式
    MCP_API_TOKEN=xxx python -m mcp_tools.mcp_server  # 带认证

Claude Desktop 配置见 docs/mcp_integration.md。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

# ── Token 验证 ──────────────────────────────────────────────────

_MCP_TOKEN = os.getenv("MCP_API_TOKEN", "")


def _check_token(arguments: dict[str, Any]) -> None:
    """若设置了 MCP_API_TOKEN，则要求调用方传入 token。"""
    if not _MCP_TOKEN:
        return
    token = arguments.pop("_token", "") or arguments.pop("token", "")
    if token != _MCP_TOKEN:
        raise PermissionError("MCP_API_TOKEN 验证失败")


# ── Server 实例 ─────────────────────────────────────────────────

server = Server("retailguard-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """注册 4 个 MCP 工具。"""
    return [
        Tool(
            name="query_order",
            description="查询订单详情。传入 order_id 返回订单状态、金额、地址等信息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号，如 ORD-1-A1B2C3D4"},
                    "tenant_id": {"type": "integer", "description": "租户 ID（可选，默认 1）"},
                },
                "required": ["order_id"],
            },
        ),
        Tool(
            name="list_refunds",
            description="列出退款工单。可按状态过滤，返回退款申请列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "工单状态过滤：open / in_progress / pending_review / resolved / closed",
                    },
                    "limit": {"type": "integer", "description": "返回条数（默认 10，最大 50）"},
                    "tenant_id": {"type": "integer", "description": "租户 ID（可选，默认 1）"},
                },
                "required": [],
            },
        ),
        Tool(
            name="get_kb_doc",
            description="查询知识库文档。按关键词搜索售后政策、退货流程等知识库内容。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，如 '7天无理由退货'"},
                    "category": {
                        "type": "string",
                        "description": "文档分类：refund / logistics / faq / promotion（可选）",
                    },
                    "tenant_id": {"type": "integer", "description": "租户 ID（可选，默认 1）"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="risk_check",
            description="风控评分。对退款请求进行三层融合风控评估，返回 pass/review/reject 决策及可解释证据链。",
            inputSchema={
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "退款金额（元）"},
                    "reason": {"type": "string", "description": "退款原因"},
                    "days_since_delivery": {"type": "integer", "description": "签收后天数"},
                    "user_refund_count_30d": {"type": "integer", "description": "用户近 30 天退款次数"},
                    "tenant_id": {"type": "integer", "description": "租户 ID（可���，默认 1）"},
                },
                "required": ["amount", "reason"],
            },
        ),
    ]


# ── 工具实现 ────────────────────────────────────────────────────

async def _query_order(arguments: dict[str, Any]) -> str:
    """查询订单。优先查 DB，fallback 到 mock 数据。"""
    order_id = arguments.get("order_id", "")
    tenant_id = arguments.get("tenant_id", 1)

    try:
        from sqlalchemy import select
        from db.session import async_session
        from db.models import Order
        from db.tenant_context import set_current_tenant

        set_current_tenant(tenant_id)
        async with async_session() as session:
            result = await session.execute(
                select(Order).where(Order.order_no == order_id, Order.tenant_id == tenant_id)
            )
            order = result.scalar_one_or_none()
            if order:
                return json.dumps({
                    "found": True,
                    "order_no": order.order_no,
                    "status": order.status,
                    "total_amount": order.total_amount,
                    "product_name": order.product_name,
                    "shipping_address": order.shipping_address,
                    "delivered_at": str(order.delivered_at) if order.delivered_at else None,
                    "created_at": str(order.created_at),
                }, ensure_ascii=False)
    except Exception as exc:
        logger.debug("query_order DB failed, using mock: %s", exc)

    # Mock fallback
    return json.dumps({
        "found": False,
        "order_id": order_id,
        "message": f"订单 {order_id} 未找到（DB 未初始化或订单不存在）",
    }, ensure_ascii=False)


async def _list_refunds(arguments: dict[str, Any]) -> str:
    """列出退款工单。"""
    status_filter = arguments.get("status", "")
    limit = min(arguments.get("limit", 10), 50)
    tenant_id = arguments.get("tenant_id", 1)

    try:
        from sqlalchemy import select
        from db.session import async_session
        from db.models import Ticket
        from db.tenant_context import set_current_tenant

        set_current_tenant(tenant_id)
        async with async_session() as session:
            query = (
                select(Ticket)
                .where(Ticket.tenant_id == tenant_id, Ticket.type == "refund")
                .order_by(Ticket.created_at.desc())
                .limit(limit)
            )
            if status_filter:
                query = query.where(Ticket.status == status_filter)
            result = await session.execute(query)
            tickets = result.scalars().all()
            return json.dumps({
                "count": len(tickets),
                "tickets": [
                    {
                        "ticket_no": t.ticket_no,
                        "status": t.status,
                        "amount": t.amount,
                        "reason": t.reason,
                        "risk_score": t.risk_score,
                        "risk_decision": t.risk_decision,
                        "created_at": str(t.created_at),
                    }
                    for t in tickets
                ],
            }, ensure_ascii=False)
    except Exception as exc:
        logger.debug("list_refunds DB failed: %s", exc)

    return json.dumps({"count": 0, "tickets": [], "note": "DB 未初始化，请运行 bootstrap.py"}, ensure_ascii=False)


async def _get_kb_doc(arguments: dict[str, Any]) -> str:
    """查询知识库文档（RAG 检索）。"""
    query = arguments.get("query", "")
    tenant_id = arguments.get("tenant_id", 1)

    try:
        from rag import retriever, reranker

        chunks = retriever.hybrid_retrieve(query=query, tenant_id=tenant_id, top_k=5)
        reranked = reranker.rerank(query=query, chunks=chunks)

        results = []
        for chunk in reranked[:3]:
            results.append({
                "doc_id": chunk.doc_id,
                "doc_no": getattr(chunk, "doc_no", ""),
                "snippet": chunk.chunk_text[:300],
                "score": getattr(chunk, "score", 0),
            })
        return json.dumps({"query": query, "results": results, "count": len(results)}, ensure_ascii=False)
    except Exception as exc:
        logger.debug("get_kb_doc failed: %s", exc)

    return json.dumps({"query": query, "results": [], "note": "知识库未初始化"}, ensure_ascii=False)


async def _risk_check(arguments: dict[str, Any]) -> str:
    """风控评分。"""
    amount = arguments.get("amount", 0)
    reason = arguments.get("reason", "")
    days_since_delivery = arguments.get("days_since_delivery", 0)
    user_refund_count_30d = arguments.get("user_refund_count_30d", 0)
    tenant_id = arguments.get("tenant_id", 1)

    refund_ctx = {
        "amount": float(amount),
        "reason": reason,
        "description": reason,
        "days_since_delivery": int(days_since_delivery),
        "days_since_order": int(days_since_delivery) + 2,
        "user_refund_count_30d": int(user_refund_count_30d),
        "refund_rate_30d": 0.0,
        "amount_zscore": 0.0,
        "device_freq_1h": 0,
        "is_duplicate_refund": False,
        "cross_tenant_anomaly": False,
    }

    try:
        from risk import evaluate

        decision = await evaluate(refund_ctx, tenant_id=tenant_id)
        return json.dumps({
            "decision": decision.decision,
            "fusion_score": decision.fusion_score,
            "explanation": decision.explanation,
            "weights": decision.weights,
            "rules_hits": [
                {"rule_id": h.rule_id, "description": h.description, "severity": h.severity}
                for h in decision.rules.hits
            ],
        }, ensure_ascii=False)
    except Exception as exc:
        logger.debug("risk_check failed: %s", exc)

    return json.dumps({"decision": "unknown", "error": str(exc)}, ensure_ascii=False)


# ── 工具分发 ────────────────────────────────────────────────────

_TOOL_HANDLERS = {
    "query_order": _query_order,
    "list_refunds": _list_refunds,
    "get_kb_doc": _get_kb_doc,
    "risk_check": _risk_check,
}


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """MCP tools/call 分发。"""
    _check_token(arguments)

    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False))]

    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=result)]
    except PermissionError as exc:
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}, ensure_ascii=False))]
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": f"工具执行失败: {exc}"}, ensure_ascii=False))]


# ── 入口 ────────────────────────────────────────────────────────

async def main() -> None:
    """stdio 模式启动 MCP 服务器。"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s :: %(message)s")
    asyncio.run(main())
