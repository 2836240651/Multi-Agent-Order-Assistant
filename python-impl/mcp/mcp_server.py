from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from governance.ticket_status import (
    TicketStatus,
    can_transition_ticket_status,
    enrich_ticket,
    is_terminal_ticket_status,
    normalize_ticket_status,
    ticket_next_step,
)
from governance.webhook import WebhookEventType, emit_webhook
from governance.sla_manager import log_operation
from governance.websocket_manager import notification_manager, agent_manager

from mcp.db import get_db_connection as _get_db_connection

load_dotenv()

DB_PATH = Path(__file__).parent / "commerce.db"

_use_mysql = os.getenv("MYSQL_HOST") is not None


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    category: str = "general"
    requires_auth: bool = False


@dataclass
class ToolCallResult:
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def _order_to_dict(row: tuple | dict, columns: list) -> dict:
    from datetime import datetime
    from decimal import Decimal
    if isinstance(row, dict):
        values = list(row.values())
    else:
        values = list(row)
    converted = []
    for v in values:
        if isinstance(v, Decimal):
            converted.append(float(v))
        elif isinstance(v, datetime):
            converted.append(v.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            converted.append(v)
    return dict(zip(columns, converted))


class MCPToolServer:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._call_log: list[ToolCallResult] = []

    def register_tool(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        category: str = "general",
        requires_auth: bool = False,
    ) -> Callable:
        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable:
            tool = ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=func,
                category=category,
                requires_auth=requires_auth,
            )
            self._tools[name] = tool
            return func

        return decorator

    def list_tools(self, category: str | None = None) -> list[dict[str, Any]]:
        tools = []
        for tool in self._tools.values():
            if category and tool.category != category:
                continue
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                    "category": tool.category,
                }
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        import time

        tool = self._tools.get(name)
        if tool is None:
            result = ToolCallResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' not found. Available: {list(self._tools.keys())}",
            )
            self._call_log.append(result)
            return result

        start = time.time()
        try:
            output = await tool.handler(**arguments)
            result = ToolCallResult(
                tool_name=name,
                success=True,
                result=output,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:  # pragma: no cover - defensive
            result = ToolCallResult(
                tool_name=name,
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

        self._call_log.append(result)
        return result

    async def handle_jsonrpc(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", 1)

        try:
            if method == "tools/list":
                result = self.list_tools(category=params.get("category"))
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                call_result = await self.call_tool(tool_name, arguments)
                result = {
                    "success": call_result.success,
                    "result": call_result.result,
                    "error": call_result.error,
                }
            elif method == "ping":
                result = {"status": "ok"}
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": req_id,
                }
            return {"jsonrpc": "2.0", "result": result, "id": req_id}
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(exc)},
                "id": req_id,
            }

    def get_call_log(self, last_n: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "tool": row.tool_name,
                "success": row.success,
                "duration_ms": row.duration_ms,
                "timestamp": row.timestamp,
                "error": row.error,
            }
            for row in self._call_log[-last_n:]
        ]


def _resp(
    *,
    success: bool,
    code: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": success,
        "code": code,
        "message": message,
        "data": data or {},
    }


def create_default_tools(server: MCPToolServer) -> MCPToolServer:
    ORDER_COLS = ["order_id", "user_id", "product_name", "amount", "status", "address",
                  "order_date", "deliver_date", "can_update_address", "refund_eligible"]
    TICKET_COLS = ["ticket_id", "user_id", "title", "description", "priority", "category",
                    "action", "status", "order_id", "created_at", "updated_at", "history",
                    "sla_due_at", "rating", "rating_comment", "rating_at", "assigned_to"]

    def _ticket_from_row(row: tuple | None) -> dict[str, Any] | None:
        if row is None:
            return None
        ticket = _order_to_dict(row, TICKET_COLS)
        ticket["history"] = json.loads(ticket["history"] or "[]")
        return enrich_ticket(ticket)

    @server.register(
        name="order_query",
        description="Query order by order id",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["order_id"],
        },
        category="order",
    )
    async def order_query(order_id: str, user_id: str = "anonymous") -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(ORDER_COLS)} FROM orders WHERE order_id = ?",
            (order_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return _resp(
                success=False,
                code="ORDER_NOT_FOUND",
                message=f"Order {order_id} was not found.",
            )
        order = _order_to_dict(row, ORDER_COLS)
        order["can_update_address"] = bool(order["can_update_address"])
        order["refund_eligible"] = bool(order["refund_eligible"])
        order["product"] = order.pop("product_name")
        if order.get("deliver_date"):
            from datetime import datetime, timedelta
            deliver_date = order["deliver_date"]
            if isinstance(deliver_date, datetime):
                deliver_dt = deliver_date
            else:
                deliver_dt = datetime.strptime(deliver_date, "%Y-%m-%d %H:%M:%S")
            refund_deadline_dt = deliver_dt + timedelta(days=7)
            order["refund_deadline"] = refund_deadline_dt.strftime("%Y-%m-%d")
        else:
            order["refund_deadline"] = None

        if user_id != "anonymous" and order["user_id"] != user_id:
            return _resp(
                success=False,
                code="ORDER_FORBIDDEN",
                message=f"Order {order_id} does not belong to user {user_id}.",
            )
        return _resp(success=True, code="OK", message="Order found.", data=order)

    @server.register(
        name="order_history",
        description="Get order status change history/timeline",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
            },
            "required": ["order_id"],
        },
        category="order",
    )
    async def order_history(order_id: str) -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT old_status, new_status, changed_at, changed_by, reason FROM order_status_history WHERE order_id = ? ORDER BY changed_at ASC",
            (order_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return _resp(
                success=False,
                code="ORDER_NOT_FOUND",
                message=f"No history found for order {order_id}.",
            )
        
        history = []
        for row in rows:
            history.append({
                "from_status": row[0],
                "to_status": row[1],
                "changed_at": row[2],
                "changed_by": row[3],
                "reason": row[4]
            })
        
        return _resp(
            success=True,
            code="OK",
            message="Order history retrieved.",
            data={"order_id": order_id, "history": history}
        )

    @server.register(
        name="order_update_address",
        description="Update shipping address when order is still mutable",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "new_address": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["order_id", "new_address"],
        },
        category="order",
    )
    async def order_update_address(
        order_id: str,
        new_address: str,
        user_id: str = "anonymous",
    ) -> dict[str, Any]:
        lookup = await order_query(order_id=order_id, user_id=user_id)
        if not lookup["success"]:
            return lookup

        order = lookup["data"]
        if not order["can_update_address"]:
            return _resp(
                success=False,
                code="ADDRESS_CHANGE_WINDOW_EXPIRED",
                message="Order can no longer update address.",
                data={"order_id": order_id, "current_status": order["status"]},
            )

        conn = _get_db_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        old_status = order['status']
        conn.execute(
            "UPDATE orders SET address = ?, status = ?, can_update_address = 0 WHERE order_id = ?",
            (new_address, "address_updated", order_id)
        )
        conn.execute(
            "INSERT INTO order_status_history (order_id, old_status, new_status, changed_at, changed_by, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, old_status, 'address_updated', now, 'user', f"地址变更为: {new_address}")
        )
        conn.commit()
        conn.close()

        return _resp(
            success=True,
            code="ADDRESS_UPDATED",
            message="地址更新成功",
            data={"order_id": order_id, "new_address": new_address},
        )

    @server.register(
        name="refund_apply",
        description="Apply refund by order id",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "reason": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["order_id", "reason"],
        },
        category="order",
    )
    async def refund_apply(
        order_id: str,
        reason: str,
        user_id: str = "anonymous",
    ) -> dict[str, Any]:
        lookup = await order_query(order_id=order_id, user_id=user_id)
        if not lookup["success"]:
            return lookup

        order = lookup["data"]
        if not order["refund_eligible"]:
            return _resp(
                success=False,
                code="REFUND_NOT_ELIGIBLE",
                message="Refund request is outside policy window.",
                data={"order_id": order_id},
            )

        refund_id = f"RF-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        conn = _get_db_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "UPDATE orders SET status = 'refund_requested', refund_eligible = 0 WHERE order_id = ?",
            (order_id,)
        )
        conn.execute(
            "INSERT INTO order_status_history (order_id, old_status, new_status, changed_at, changed_by, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, order['status'], 'refund_requested', now, 'user', f"退款申请: {reason}")
        )
        conn.commit()
        conn.close()

        return _resp(
            success=True,
            code="REFUND_REQUESTED",
            message="退款申请已提交，等待审核处理",
            data={
                "order_id": order_id,
                "refund_id": refund_id,
                "reason": reason,
                "review_status": "pending_review",
            },
        )

    @server.register(
        name="ticket_create",
        description="Create support ticket",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string"},
                "category": {"type": "string"},
                "order_id": {"type": "string"},
                "user_id": {"type": "string"},
                "action": {"type": "string"},
            },
            "required": ["title", "description"],
        },
        category="ticket",
    )
    async def ticket_create(
        title: str,
        description: str,
        priority: str = "medium",
        category: str = "general",
        order_id: str = "",
        user_id: str = "anonymous",
        action: str = "general_inquiry",
    ) -> dict[str, Any]:
        from governance.sla_manager import compute_sla_due
        ticket_id = f"TK-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        now = datetime.now().isoformat()
        sla_due_at = await compute_sla_due(priority, now)
        history = json.dumps(
            [
                {
                    "status": TicketStatus.CREATED.value,
                    "note": "Ticket created.",
                    "timestamp": now,
                }
            ]
        )

        conn = _get_db_connection()
        try:
            conn.execute(
                f"""INSERT INTO tickets 
                ({', '.join(TICKET_COLS)})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticket_id, user_id, title, description, priority, category,
                 action, TicketStatus.CREATED.value, order_id, now, now, history,
                 sla_due_at, None, "", "", "")
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.close()
            if "idx_tickets_pending_dedup" in str(exc) or "UNIQUE constraint failed" in str(exc):
                conn2 = _get_db_connection()
                cursor = conn2.execute(
                    f"SELECT {', '.join(TICKET_COLS)} FROM tickets WHERE order_id = ? AND action = ? AND status NOT IN ('resolved', 'rejected', 'closed') ORDER BY created_at DESC LIMIT 1",
                    (order_id, action)
                )
                row = cursor.fetchone()
                conn2.close()
                if row:
                    result = _ticket_from_row(row)
                    return _resp(
                        success=True,
                        code="TICKET_REUSED",
                        message="Existing active ticket found, reusing it.",
                        data=result,
                    )
            raise

        cursor = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        conn.close()

        result = _ticket_from_row(row)
        asyncio.create_task(_emit_ticket_webhooks(ticket_id, "", TicketStatus.CREATED.value, result))
        asyncio.create_task(_emit_ticket_created_notification(result))
        return _resp(success=True, code="TICKET_CREATED", message="Ticket created.", data=result)

    @server.register(
        name="ticket_update",
        description="Update support ticket status",
        input_schema={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "status": {"type": "string"},
                "note": {"type": "string"},
                "next_step": {"type": "string"},
            },
            "required": ["ticket_id", "status"],
        },
        category="ticket",
    )
    async def _emit_ticket_webhooks(ticket_id: str, from_status: str, to_status: str, ticket_data: dict):
        now = datetime.now().isoformat()
        payload = {
            "event": WebhookEventType.TICKET_STATUS_CHANGED.value,
            "ticket_id": ticket_id,
            "from_status": from_status,
            "to_status": to_status,
            "ticket": ticket_data,
            "timestamp": now,
        }
        await emit_webhook(WebhookEventType.TICKET_STATUS_CHANGED.value, payload)
        if to_status == TicketStatus.RESOLVED.value:
            payload["event"] = WebhookEventType.TICKET_RESOLVED.value
            await emit_webhook(WebhookEventType.TICKET_RESOLVED.value, payload)
        elif to_status == TicketStatus.REJECTED.value:
            payload["event"] = WebhookEventType.TICKET_REJECTED.value
            await emit_webhook(WebhookEventType.TICKET_REJECTED.value, payload)
        elif to_status == TicketStatus.CLOSED.value:
            payload["event"] = WebhookEventType.TICKET_CLOSED.value
            await emit_webhook(WebhookEventType.TICKET_CLOSED.value, payload)

        await notification_manager.broadcast({
            "type": "ticket_update",
            "ticket_id": ticket_id,
            "from_status": from_status,
            "to_status": to_status,
            "ticket": ticket_data,
            "timestamp": now,
        })
        await agent_manager.broadcast({
            "type": "ticket_update",
            "ticket_id": ticket_id,
            "from_status": from_status,
            "to_status": to_status,
            "ticket": ticket_data,
            "timestamp": now,
        })

    async def _emit_ticket_created_notification(ticket_data: dict):
        now = datetime.now().isoformat()
        payload = {
            "type": "ticket_created",
            "ticket": ticket_data,
            "timestamp": now,
        }
        await notification_manager.broadcast(payload)
        await agent_manager.broadcast(payload)

    async def ticket_update(ticket_id: str, status: str, note: str = "", next_step: str = "") -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.execute(
            "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return _resp(
                success=False,
                code="TICKET_NOT_FOUND",
                message=f"Ticket {ticket_id} was not found.",
            )

        ticket = _order_to_dict(row, TICKET_COLS)
        current_status = normalize_ticket_status(ticket["status"])
        target_status = normalize_ticket_status(status)
        if not can_transition_ticket_status(current_status, target_status):
            conn.close()
            return _resp(
                success=False,
                code="TICKET_INVALID_TRANSITION",
                message=f"Invalid ticket transition: {current_status} -> {target_status}.",
                data={
                    "ticket_id": ticket_id,
                    "current_status": current_status,
                    "target_status": target_status,
                },
            )

        history = json.loads(ticket["history"] or "[]")

        now = datetime.now().isoformat()
        history.append(
            {
                "status": target_status,
                "note": note or "Updated by system.",
                "timestamp": now,
                "next_step": next_step if next_step else ticket_next_step(target_status),
            }
        )
        conn.execute(
            "UPDATE tickets SET status = ?, updated_at = ?, history = ? WHERE ticket_id = ?",
            (target_status, now, json.dumps(history), ticket_id)
        )
        conn.commit()

        asyncio.create_task(log_operation(
            _get_db_connection,
            operator_id="system",
            operator_type="system",
            target_type="ticket",
            target_id=ticket_id,
            action=f"status_change:{current_status}->{target_status}",
            detail=note or f"Status changed from {current_status} to {target_status}",
            before_state=json.dumps({"status": current_status}),
            after_state=json.dumps({"status": target_status}),
        ))

        cursor = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        conn.close()

        result = _ticket_from_row(row)

        asyncio.create_task(_emit_ticket_webhooks(ticket_id, current_status, target_status, result))

        return _resp(success=True, code="TICKET_UPDATED", message="Ticket updated.", data=result)

    @server.register(
        name="ticket_query",
        description="Query support ticket",
        input_schema={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["ticket_id"],
        },
        category="ticket",
    )
    async def ticket_query(ticket_id: str, user_id: str = "anonymous") -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.execute(
            f"SELECT {', '.join(TICKET_COLS)} FROM tickets WHERE ticket_id = ?",
            (ticket_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return _resp(
                success=False,
                code="TICKET_NOT_FOUND",
                message=f"Ticket {ticket_id} was not found.",
            )
        ticket = _ticket_from_row(row)

        if user_id != "anonymous" and ticket["user_id"] != user_id:
            return _resp(
                success=False,
                code="TICKET_FORBIDDEN",
                message=f"Ticket {ticket_id} does not belong to user {user_id}.",
            )
        return _resp(success=True, code="OK", message="Ticket found.", data=ticket)

    @server.register(
        name="ticket_list",
        description="List support tickets by user/order/status",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "order_id": {"type": "string"},
                "action": {"type": "string"},
                "status": {"type": "string"},
                "include_closed": {"type": "boolean"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        category="ticket",
    )
    async def ticket_list(
        user_id: str = "",
        order_id: str = "",
        action: str = "",
        status: str = "",
        include_closed: bool = True,
        limit: int = 50,
    ) -> dict[str, Any]:
        conn = _get_db_connection()
        query = f"SELECT {', '.join(TICKET_COLS)} FROM tickets WHERE 1=1"
        params: list[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if order_id:
            query += " AND order_id = ?"
            params.append(order_id)
        if action:
            query += " AND action = ?"
            params.append(action)
        if status:
            query += " AND status = ?"
            params.append(normalize_ticket_status(status))
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        tickets = [_ticket_from_row(row) for row in rows]
        if not include_closed:
            tickets = [ticket for ticket in tickets if not is_terminal_ticket_status(ticket["status"])]
        return _resp(
            success=True,
            code="OK",
            message="Tickets listed.",
            data={"items": tickets, "total": len(tickets)},
        )

    @server.register(
        name="risk_check",
        description="Risk scoring API (mock)",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "action": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["user_id", "action"],
        },
        category="compliance",
    )
    async def risk_check(user_id: str, action: str, amount: float = 0.0) -> dict[str, Any]:
        risk_level = "low"
        if amount >= 1000:
            risk_level = "medium"
        if amount >= 10000:
            risk_level = "high"

        return _resp(
            success=True,
            code="OK",
            message="Risk score generated.",
            data={
                "user_id": user_id,
                "action": action,
                "risk_level": risk_level,
                "requires_manual_review": risk_level == "high",
            },
        )

    @server.register(
        name="logistics_query",
        description="Query logistics/shipping status by order id or tracking number",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "tracking_number": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": [],
        },
        category="logistics",
    )
    async def logistics_query(
        order_id: str = "",
        tracking_number: str = "",
        user_id: str = "anonymous",
    ) -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.cursor()

        if tracking_number:
            cursor.execute(
                "SELECT * FROM logistics WHERE tracking_number = ?",
                (tracking_number,)
            )
        elif order_id:
            cursor.execute(
                "SELECT * FROM logistics WHERE order_id = ?",
                (order_id,)
            )
        else:
            conn.close()
            return _resp(
                success=False,
                code="LOGISTICS_PARAM_REQUIRED",
                message="Please provide order_id or tracking_number.",
            )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return _resp(
                success=False,
                code="LOGISTICS_NOT_FOUND",
                message="Logistics information not found.",
            )

        LOGISTICS_COLS = [
            "logistics_id", "order_id", "express_company", "express_company_code",
            "tracking_number", "status", "sender_address", "receiver_address",
            "weight", "fee", "channel", "package_count", "insure_fee",
            "signer", "estimated_delivery", "delivered_at", "created_at", "updated_at"
        ]
        logistics = _order_to_dict(row, LOGISTICS_COLS)

        if order_id and user_id != "anonymous":
            cursor2 = conn.cursor()
            cursor2.execute("SELECT user_id FROM orders WHERE order_id = ?", (order_id,))
            order_row = cursor2.fetchone()
            if order_row and order_row[0] != user_id:
                conn.close()
                return _resp(
                    success=False,
                    code="LOGISTICS_FORBIDDEN",
                    message=f"Logistics for order {order_id} does not belong to user {user_id}.",
                )

        return _resp(success=True, code="OK", message="Logistics found.", data=logistics)

    @server.register(
        name="logistics_tracking",
        description="Query logistics tracking history",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "tracking_number": {"type": "string"},
            },
            "required": ["order_id"],
        },
        category="logistics",
    )
    async def logistics_tracking(
        order_id: str = "",
        tracking_number: str = "",
    ) -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.cursor()

        if tracking_number:
            cursor.execute(
                "SELECT logistics_id FROM logistics WHERE tracking_number = ?",
                (tracking_number,)
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return _resp(
                    success=False,
                    code="LOGISTICS_NOT_FOUND",
                    message="Logistics information not found.",
                )
            logistics_id = row[0]
        elif order_id:
            cursor.execute(
                "SELECT logistics_id FROM logistics WHERE order_id = ?",
                (order_id,)
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return _resp(
                    success=False,
                    code="LOGISTICS_NOT_FOUND",
                    message="Logistics information not found for this order.",
                )
            logistics_id = row[0]
        else:
            conn.close()
            return _resp(
                success=False,
                code="LOGISTICS_PARAM_REQUIRED",
                message="Please provide order_id or tracking_number.",
            )

        cursor.execute(
            "SELECT * FROM logistics_tracking WHERE logistics_id = ? ORDER BY timestamp ASC",
            (logistics_id,)
        )
        tracking_rows = cursor.fetchall()
        conn.close()

        TRACKING_COLS = [
            "tracking_id", "logistics_id", "status", "location", "description", "operator", "timestamp", "created_at"
        ]

        STATUS_MAP = {
            "pending": "待发货",
            "picked_up": "已揽收",
            "in_transit": "运输中",
            "out_for_delivery": "派送中",
            "delivered": "已签收",
            "returned": "已退回",
            "exception": "异常",
        }

        tracking_list = []
        for tr_row in tracking_rows:
            tr = _order_to_dict(tr_row, TRACKING_COLS)
            tr["status_text"] = STATUS_MAP.get(tr["status"], tr["status"])
            tracking_list.append(tr)

        return _resp(
            success=True,
            code="OK",
            message="Tracking history found.",
            data={"tracking": tracking_list},
        )

    @server.register(
        name="logistics_expedite",
        description="Request expedited shipping for an order (urge shipment)",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "user_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["order_id"],
        },
        category="logistics",
    )
    async def logistics_expedite(
        order_id: str,
        user_id: str = "anonymous",
        reason: str = "",
    ) -> dict[str, Any]:
        order_lookup = await order_query(order_id=order_id, user_id=user_id)
        if not order_lookup["success"]:
            return order_lookup

        order_status = order_lookup["data"]["status"]
        if order_status not in ["pending", "processing"]:
            return _resp(
                success=False,
                code="LOGISTICS_EXPEDITE_NOT_ALLOWED",
                message=f"Cannot expedite order in status: {order_status}. Only pending or processing orders can be expedited.",
                data={"order_id": order_id, "current_status": order_status},
            )

        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT logistics_id, status FROM logistics WHERE order_id = ?",
            (order_id,)
        )
        log_row = cursor.fetchone()
        conn.close()

        if not log_row:
            return _resp(
                success=False,
                code="LOGISTICS_NOT_FOUND",
                message="No logistics record found for this order.",
            )

        logistics_id, logistics_status = log_row
        if logistics_status not in ["pending", "picked_up"]:
            return _resp(
                success=False,
                code="LOGISTICS_EXPEDITE_TOO_LATE",
                message="Too late to expedite. Package has already been picked up by courier.",
                data={"order_id": order_id, "logistics_status": logistics_status},
            )

        title = f"催促发货 - 订单 {order_id}"
        description = f"用户 {user_id} 催促发货。原因: {reason or '未说明'}"

        ticket_result = await ticket_create(
            title=title,
            description=description,
            priority="high",
            category="logistics_expedite",
            order_id=order_id,
            user_id=user_id,
            action="logistics_expedite",
        )
        if not ticket_result["success"]:
            return ticket_result

        ticket_id = ticket_result["data"]["ticket_id"]

        await ticket_update(
            ticket_id=ticket_id,
            status="pending",
            note="已通知仓库加急处理",
        )

        return _resp(
            success=True,
            code="LOGISTICS_EXPEDITE_CREATED",
            message="催促发货工单已创建，仓库将加急处理。",
            data={
                "order_id": order_id,
                "ticket_id": ticket_id,
                "status": "pending",
            },
        )

    @server.register(
        name="ticket_search",
        description="Advanced ticket search with filters",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "order_id": {"type": "string"},
                "status_in": {"type": "array", "items": {"type": "string"}},
                "priority_in": {"type": "array", "items": {"type": "string"}},
                "action_in": {"type": "array", "items": {"type": "string"}},
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
                "keyword": {"type": "string"},
                "include_closed": {"type": "boolean"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
            "required": [],
        },
        category="ticket",
    )
    async def ticket_search(
        user_id: str = "",
        order_id: str = "",
        status_in: list[str] | None = None,
        priority_in: list[str] | None = None,
        action_in: list[str] | None = None,
        date_from: str = "",
        date_to: str = "",
        keyword: str = "",
        include_closed: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        conn = _get_db_connection()
        query = f"SELECT {', '.join(TICKET_COLS)} FROM tickets WHERE 1=1"
        params: list[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if order_id:
            query += " AND order_id = ?"
            params.append(order_id)
        if status_in:
            placeholders = ", ".join("?" * len(status_in))
            query += f" AND status IN ({placeholders})"
            params.extend(status_in)
        if priority_in:
            placeholders = ", ".join("?" * len(priority_in))
            query += f" AND priority IN ({placeholders})"
            params.extend(priority_in)
        if action_in:
            placeholders = ", ".join("?" * len(action_in))
            query += f" AND action IN ({placeholders})"
            params.extend(action_in)
        if date_from:
            query += " AND created_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND created_at <= ?"
            params.append(date_to)
        if keyword:
            query += " AND (title LIKE ? OR description LIKE ?)"
            like_kw = f"%{keyword}%"
            params.extend([like_kw, like_kw])
        if not include_closed:
            query += " AND status NOT IN ('resolved', 'rejected', 'closed')"
        if _use_mysql:
            count_query = f"SELECT COUNT(*) FROM ({query}) AS cnt"
            count_cursor = conn.execute(count_query, params)
        else:
            count_query = f"SELECT COUNT(*) FROM ({query})"
            count_cursor = conn.execute(count_query, params)
        count_row = count_cursor.fetchone()
        total = count_row[0] if count_row else 0
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, min(limit, 200)), max(0, offset)])
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        tickets = [_ticket_from_row(row) for row in rows]
        return _resp(
            success=True,
            code="OK",
            message="Tickets searched.",
            data={"items": tickets, "total": total, "limit": limit, "offset": offset},
        )

    @server.register(
        name="ticket_rate",
        description="Rate a resolved ticket",
        input_schema={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "user_id": {"type": "string"},
                "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                "rating_comment": {"type": "string"},
            },
            "required": ["ticket_id", "user_id", "rating"],
        },
        category="ticket",
    )
    async def ticket_rate(ticket_id: str, user_id: str, rating: int, rating_comment: str = "") -> dict[str, Any]:
        from governance.sla_manager import rate_ticket as sla_rate_ticket
        result = await sla_rate_ticket(_get_db_connection, ticket_id, user_id, rating, rating_comment)
        return _resp(
            success=result.get("success", False),
            code="TICKET_RATED" if result.get("success") else "TICKET_RATING_FAILED",
            message=result.get("message", ""),
            data=result.get("data", {}),
        )

    @server.register(
        name="chat_messages_mark_read",
        description="Mark chat messages as read",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "user_id": {"type": "string"},
                "message_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["session_id", "user_id"],
        },
        category="chat",
    )
    async def chat_messages_mark_read(session_id: str, user_id: str, message_ids: list[str] | None = None) -> dict[str, Any]:
        now = datetime.now().isoformat()
        conn = _get_db_connection()
        if message_ids:
            placeholders = ", ".join("?" * len(message_ids))
            conn.execute(
                f"UPDATE chat_messages SET is_read = 1, read_at = ? WHERE session_id = ? AND user_id = ? AND message_id IN ({placeholders})",
                [now, session_id, user_id] + message_ids,
            )
        else:
            conn.execute(
                "UPDATE chat_messages SET is_read = 1, read_at = ? WHERE session_id = ? AND user_id = ? AND is_read = 0",
                (now, session_id, user_id),
            )
        conn.commit()
        conn.close()
        return _resp(success=True, code="MESSAGES_READ", message="Messages marked as read.")

    @server.register(
        name="chat_unread_count",
        description="Get unread message count",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["session_id", "user_id"],
        },
        category="chat",
    )
    async def chat_unread_count(session_id: str, user_id: str) -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND user_id = ? AND is_read = 0 AND role = 'assistant'",
            (session_id, user_id),
        )
        row = cursor.fetchone()
        conn.close()
        count = row[0] if row else 0
        return _resp(success=True, code="OK", message="Unread count.", data={"session_id": session_id, "unread_count": count})

    @server.register(
        name="check_overdue_tickets",
        description="Check and trigger reminders for overdue tickets",
        input_schema={
            "type": "object",
            "properties": {
                "batch_size": {"type": "integer", "default": 50},
            },
            "required": [],
        },
        category="ticket",
    )
    async def check_overdue_tickets_mcp(batch_size: int = 50) -> dict[str, Any]:
        from governance.sla_manager import check_overdue_tickets as check_overdue, send_overdue_reminder
        overdue = await check_overdue(_get_db_connection, batch_size)
        sent = []
        for ticket in overdue:
            reminder_id = await send_overdue_reminder(_get_db_connection, ticket)
            sent.append({"ticket_id": ticket["ticket_id"], "reminder_id": reminder_id})
        return _resp(
            success=True,
            code="OVERDUE_CHECK_COMPLETE",
            message=f"Checked {len(overdue)} overdue tickets, sent {len(sent)} reminders.",
            data={"overdue_count": len(overdue), "reminders_sent": sent},
        )

    @server.register(
        name="operational_log_query",
        description="Query operational audit logs",
        input_schema={
            "type": "object",
            "properties": {
                "operator_id": {"type": "string"},
                "target_type": {"type": "string"},
                "target_id": {"type": "string"},
                "action": {"type": "string"},
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        category="audit",
    )
    async def operational_log_query(
        operator_id: str = "",
        target_type: str = "",
        target_id: str = "",
        action: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 100,
    ) -> dict[str, Any]:
        from governance.sla_manager import search_operational_logs
        logs = await search_operational_logs(
            _get_db_connection,
            operator_id=operator_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        return _resp(success=True, code="OK", message="Logs queried.", data={"items": logs, "total": len(logs)})

    @server.register(
        name="ticket_assign",
        description="Assign a ticket to an operator/agent",
        input_schema={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "assigned_to": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["ticket_id", "assigned_to"],
        },
        category="ticket",
    )
    async def ticket_assign(ticket_id: str, assigned_to: str, note: str = "") -> dict[str, Any]:
        conn = _get_db_connection()
        cursor = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return _resp(success=False, code="TICKET_NOT_FOUND", message=f"Ticket {ticket_id} not found.")
        now = datetime.now().isoformat()
        history = json.loads(row[11] or "[]")
        history.append(
            {
                "status": normalize_ticket_status(row[7]),
                "note": note or f"Assigned to {assigned_to}.",
                "timestamp": now,
                "next_step": ticket_next_step(row[7]),
            }
        )
        conn.execute(
            "UPDATE tickets SET assigned_to = ?, updated_at = ?, history = ? WHERE ticket_id = ?",
            (assigned_to, now, json.dumps(history), ticket_id),
        )
        conn.commit()
        conn.close()
        return _resp(success=True, code="TICKET_ASSIGNED", message=f"Ticket assigned to {assigned_to}.")

    return server
