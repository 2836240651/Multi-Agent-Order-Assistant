from __future__ import annotations

import re
from typing import Any

from langchain_openai import ChatOpenAI

from governance.ticket_status import TicketStatus
from governance.workflow_status import ExecutionStatus, execution_status_label
from mcp.mcp_server import MCPToolServer
from tracing.otel_config import trace_agent_call


ORDER_ID_PATTERN = re.compile(r"ORD-\d{8}-\d{4}", re.IGNORECASE)
TICKET_ID_PATTERN = re.compile(r"TK-\d{8}-[A-Z0-9]{6}", re.IGNORECASE)
ADDRESS_WITH_COLON_PATTERN = re.compile(r"地址[:：]?\s*(.+)$")
ADDRESS_FALLBACK_PATTERN = re.compile(r"地址\s+(.+)$")


class TicketHandlerAgent:
    def __init__(self, llm: ChatOpenAI, mcp_server: MCPToolServer):
        self.llm = llm
        self.mcp_server = mcp_server

    def _extract_order_id(self, text: str) -> str:
        match = ORDER_ID_PATTERN.search(text or "")
        return match.group(0).upper() if match else ""

    def _extract_ticket_id(self, text: str) -> str:
        match = TICKET_ID_PATTERN.search(text or "")
        return match.group(0).upper() if match else ""

    def _extract_new_address(self, text: str) -> str:
        match = ADDRESS_WITH_COLON_PATTERN.search(text or "") or ADDRESS_FALLBACK_PATTERN.search(text or "")
        if not match:
            return ""
        return match.group(1).strip().strip("，,。.;；")

    def _extract_refund_reason(self, text: str) -> str:
        normalized = text or ""
        for splitter in ["因为", "原因", "reason"]:
            if splitter in normalized:
                return normalized.split(splitter, 1)[-1].strip()
        return "User requested refund."

    def _resolve_order_id(self, user_message: str, state: dict[str, Any] | None = None) -> str:
        order_id = self._extract_order_id(user_message)
        if order_id:
            return order_id
        entities = (state or {}).get("entities", {})
        if entities.get("order_id"):
            return entities["order_id"]
        return (state or {}).get("context_order_id", "")

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self.mcp_server.call_tool(name, arguments)
        if result.success:
            return result.result
        return {
            "success": False,
            "code": "TOOL_CALL_FAILED",
            "message": result.error or f"{name} failed.",
            "data": {},
        }

    def _workflow_response(
        self,
        *,
        execution_status: str,
        code: str,
        message: str,
        action: str,
        next_step: str,
        ticket: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ticket = ticket or {}
        return {
            "execution_status": execution_status,
            "execution_status_label": execution_status_label(execution_status),
            "code": code,
            "message": message,
            "ticket_id": ticket.get("ticket_id", ""),
            "ticket_status": ticket.get("ticket_status", ""),
            "ticket_status_label": ticket.get("ticket_status_label", ""),
            "action": action,
            "next_step": next_step,
            "result": result or {},
        }

    def _execution_status_for_ticket(self, ticket_status: str) -> str:
        if ticket_status == TicketStatus.PENDING_USER_CONFIRM.value:
            return ExecutionStatus.WAITING_USER_INPUT.value
        if ticket_status == TicketStatus.PENDING_MANUAL_REVIEW.value:
            return ExecutionStatus.WAITING_MANUAL_REVIEW.value
        if ticket_status in {
            TicketStatus.CREATED.value,
            TicketStatus.PENDING.value,
            TicketStatus.PENDING_REVIEW.value,
            TicketStatus.IN_PROGRESS.value,
        }:
            return ExecutionStatus.SUBMITTED.value
        if ticket_status == TicketStatus.REJECTED.value:
            return ExecutionStatus.FAILED.value
        return ExecutionStatus.EXECUTED.value

    def _existing_ticket_response(
        self,
        *,
        ticket: dict[str, Any],
        action: str,
        default_message: str,
    ) -> dict[str, Any]:
        execution_status = self._execution_status_for_ticket(ticket.get("ticket_status", ""))
        return self._workflow_response(
            execution_status=execution_status,
            code="TICKET_ALREADY_OPEN",
            message=default_message,
            action=action,
            next_step="可在下方查看工单进度。",
            ticket=ticket,
            result=ticket,
        )

    async def _get_ticket(self, ticket_id: str, user_id: str) -> dict[str, Any] | None:
        if not ticket_id:
            return None
        payload = await self._call_tool("ticket_query", {"ticket_id": ticket_id, "user_id": user_id})
        if payload.get("success"):
            return payload.get("data", {})
        return None

    async def _find_open_ticket(self, *, user_id: str, order_id: str, action: str) -> dict[str, Any] | None:
        if not order_id:
            return None
        payload = await self._call_tool(
            "ticket_list",
            {
                "user_id": user_id,
                "order_id": order_id,
                "action": action,
                "include_closed": False,
                "limit": 20,
            },
        )
        if not payload.get("success"):
            return None
        items = payload.get("data", {}).get("items", [])
        return items[0] if items else None

    async def _ensure_ticket(
        self,
        *,
        user_id: str,
        order_id: str,
        action: str,
        title: str,
        description: str,
        priority: str,
        target_status: str,
        note: str,
        existing_ticket_id: str = "",
        next_step: str = "",
    ) -> dict[str, Any]:
        ticket = await self._get_ticket(existing_ticket_id, user_id) if existing_ticket_id else None
        if ticket is None:
            ticket = await self._find_open_ticket(user_id=user_id, order_id=order_id, action=action)

        if ticket is None:
            created = await self._call_tool(
                "ticket_create",
                {
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "category": action,
                    "order_id": order_id,
                    "user_id": user_id,
                    "action": action,
                },
            )
            if not created.get("success"):
                return {}
            ticket = created.get("data", {})

        if ticket.get("ticket_status") != target_status:
            update_args = {
                "ticket_id": ticket["ticket_id"],
                "status": target_status,
                "note": note,
            }
            if next_step:
                update_args["next_step"] = next_step
            updated = await self._call_tool(
                "ticket_update",
                update_args,
            )
            if updated.get("success"):
                return updated.get("data", {})

        return ticket

    @trace_agent_call("ticket_query")
    async def _handle_ticket_query(self, user_message: str, user_id: str) -> dict[str, Any]:
        ticket_id = self._extract_ticket_id(user_message)
        if not ticket_id:
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="TICKET_ID_REQUIRED",
                message="请提供工单号，例如 TK-20260410-ABC123。",
                action="ticket_query",
                next_step="请提供您的工单号。",
            )

        payload = await self._call_tool("ticket_query", {"ticket_id": ticket_id, "user_id": user_id})
        if not payload.get("success"):
            return self._workflow_response(
                execution_status=ExecutionStatus.FAILED.value,
                code=payload.get("code", "TICKET_QUERY_FAILED"),
                message="抱歉，查询工单失败，请稍后重试。",
                action="ticket_query",
                next_step="请确认工单号是否正确。",
            )

        ticket = payload["data"]
        return self._workflow_response(
            execution_status=ExecutionStatus.EXECUTED.value,
            code="TICKET_FOUND",
            message=f"工单 {ticket_id} 当前状态：{ticket.get('ticket_status_label', '处理中')}。",
            action="ticket_query",
            next_step=ticket.get("ticket_next_step", "如有其他问题请随时告诉我。"),
            ticket=ticket,
            result=ticket,
        )

    @trace_agent_call("order_query")
    async def _handle_order_query(
        self,
        user_message: str,
        user_id: str,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        order_id = self._resolve_order_id(user_message, state)
        if not order_id:
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="ORDER_ID_REQUIRED",
                message="Please provide or select an order first.",
                action="order_query",
                next_step="Choose an order in the dashboard or include the order id in your message.",
            )

        payload = await self._call_tool("order_query", {"order_id": order_id, "user_id": user_id})
        if not payload.get("success"):
            return self._workflow_response(
                execution_status=ExecutionStatus.FAILED.value,
                code=payload.get("code", "ORDER_QUERY_FAILED"),
                message=payload.get("message", "Order query failed."),
                action="order_query",
                next_step="Verify the order id and account ownership.",
                result=payload.get("data", {}),
            )

        ORDER_STATUS_LABELS = {
            "pending": "待支付",
            "paid": "已支付",
            "processing": "处理中",
            "shipped": "已发货",
            "delivered": "已送达",
            "cancelled": "已取消",
            "refunded": "已退款",
            "refund_pending": "退款中",
            "completed": "已完成",
        }

        history_payload = await self._call_tool("order_history", {"order_id": order_id})
        order_data = payload["data"]
        order_data["history"] = history_payload.get("data", {}).get("history", [])

        history_lines = []
        for item in order_data["history"]:
            history_status = ORDER_STATUS_LABELS.get(item.get('to_status', ''), item.get('to_status', ''))
            history_lines.append(
                f"- {item.get('changed_at', '')[:16]} | {history_status} | {item.get('reason', '')}"
            )

        order_status = order_data.get('status', 'unknown')
        status_label = ORDER_STATUS_LABELS.get(order_status, order_status)

        message_lines = [
            f"订单号：{order_id}",
            f"商品：{order_data.get('product', 'N/A')}",
            f"金额：¥{order_data.get('amount', 0):.2f}",
            f"状态：{status_label}",
            f"收货地址：{order_data.get('address', 'N/A')}",
        ]
        if history_lines:
            message_lines.append("订单历史：")
            message_lines.extend(history_lines)

        return self._workflow_response(
            execution_status=ExecutionStatus.EXECUTED.value,
            code="ORDER_FOUND",
            message="\n".join(message_lines),
            action="order_query",
            next_step="如有退款、改地址、催发货等需求，请在本订单对话中告诉我。",
            result=order_data,
        )

    @trace_agent_call("address_change")
    async def _handle_address_change(
        self,
        user_message: str,
        user_id: str,
        existing_ticket_id: str = "",
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = "order_update_address"
        order_id = self._resolve_order_id(user_message, state)
        if not order_id:
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="ORDER_ID_REQUIRED",
                message="请先选择一个订单，我来帮您修改收货地址。",
                action=action,
                next_step="请先在订单列表中选择要修改地址的订单。",
            )

        open_ticket = None
        if not existing_ticket_id:
            open_ticket = await self._find_open_ticket(user_id=user_id, order_id=order_id, action=action)
            if open_ticket and open_ticket.get("ticket_status") not in {
                TicketStatus.CREATED.value,
                TicketStatus.PENDING_USER_CONFIRM.value,
            }:
                return self._existing_ticket_response(
                    ticket=open_ticket,
                    action=action,
                    default_message="该订单已有地址修改申请在处理中，请等待处理完成。",
                )

        new_address = self._extract_new_address(user_message)
        effective_ticket_id = existing_ticket_id or (open_ticket or {}).get("ticket_id", "")
        if not new_address:
            ticket = await self._ensure_ticket(
                user_id=user_id,
                order_id=order_id,
                action=action,
                title=f"地址确认：订单 {order_id}",
                description=user_message,
                priority="medium",
                target_status=TicketStatus.PENDING_USER_CONFIRM.value,
                note="等待用户提供新地址。",
                existing_ticket_id=effective_ticket_id,
                next_step="请回复您的新收货地址，例如：上海市浦东新区XX路XX号。",
            )
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="NEW_ADDRESS_REQUIRED",
                message="请在对话框中提供新的收货地址（例如：上海市浦东新区XX路XX号）。",
                action=action,
                next_step="请回复您的新收货地址。",
                ticket=ticket,
            )

        order_payload = await self._call_tool("order_query", {"order_id": order_id, "user_id": user_id})
        if not order_payload.get("success"):
            return self._workflow_response(
                execution_status=ExecutionStatus.FAILED.value,
                code=order_payload.get("code", "ORDER_QUERY_FAILED"),
                message="抱歉，查询订单信息失败。",
                action=action,
                next_step="请确认订单号是否正确。",
            )

        payload = await self._call_tool(
            "order_update_address",
            {"order_id": order_id, "new_address": new_address, "user_id": user_id},
        )
        if payload.get("success"):
            ticket = await self._ensure_ticket(
                user_id=user_id,
                order_id=order_id,
                action=action,
                title=f"地址已更新：订单 {order_id}",
                description=f"新地址：{new_address}",
                priority="medium",
                target_status=TicketStatus.RESOLVED.value,
                note="地址修改已完成。",
                existing_ticket_id=effective_ticket_id,
            )
            return self._workflow_response(
                execution_status=ExecutionStatus.EXECUTED.value,
                code=payload.get("code", "ADDRESS_UPDATED"),
                message=f"收货地址已更新为：{new_address}",
                action=action,
                next_step="地址修改已完成，请注意查收快递。",
                ticket=ticket,
                result=payload.get("data", {}),
            )

        ticket = await self._ensure_ticket(
            user_id=user_id,
            order_id=order_id,
            action=action,
            title=f"Address change failed for {order_id}",
            description=payload.get("message", "Address update failed."),
            priority="high",
            target_status=TicketStatus.REJECTED.value,
            note=payload.get("code", "Address update failed."),
            existing_ticket_id=effective_ticket_id,
        )
        return self._workflow_response(
            execution_status=ExecutionStatus.FAILED.value,
            code=payload.get("code", "ADDRESS_UPDATE_FAILED"),
            message=payload.get("message", "Address update failed."),
            action=action,
            next_step="Contact support if this order still needs a manual address update.",
            ticket=ticket,
            result=payload.get("data", {}),
        )

    @trace_agent_call("refund_apply")
    async def _handle_refund(
        self,
        user_message: str,
        user_id: str,
        existing_ticket_id: str = "",
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = "refund_apply"
        order_id = self._resolve_order_id(user_message, state)
        if not order_id:
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="ORDER_ID_REQUIRED",
                message="请先选择一个订单，我来帮您处理退款。",
                action=action,
                next_step="请先在订单列表中选择要退款的订单。",
            )

        if not existing_ticket_id:
            open_ticket = await self._find_open_ticket(user_id=user_id, order_id=order_id, action=action)
            if open_ticket:
                return self._existing_ticket_response(
                    ticket=open_ticket,
                    action=action,
                    default_message="该订单已有退款申请在处理中，请等待处理完成。",
                )

        order_payload = await self._call_tool("order_query", {"order_id": order_id, "user_id": user_id})
        if not order_payload.get("success"):
            return self._workflow_response(
                execution_status=ExecutionStatus.FAILED.value,
                code="ORDER_QUERY_FAILED",
                message="无法查询订单信息，请稍后重试。",
                action=action,
                next_step="请稍后重试。",
            )

        order_data = order_payload.get("data", {})
        if not order_data.get("refund_eligible"):
            refund_deadline = order_data.get("refund_deadline") or "订单送达后7天内"
            return self._workflow_response(
                execution_status=ExecutionStatus.FAILED.value,
                code="REFUND_NOT_ELIGIBLE",
                message=f"该订单已超过退款时限（{refund_deadline}），无法申请退款。",
                action=action,
                next_step="如需帮助请联系人工客服。",
            )

        payload = await self._call_tool(
            "refund_apply",
            {"order_id": order_id, "reason": self._extract_refund_reason(user_message), "user_id": user_id},
        )
        if payload.get("success"):
            ticket = await self._ensure_ticket(
                user_id=user_id,
                order_id=order_id,
                action=action,
                title=f"退款申请：订单 {order_id}",
                description=self._extract_refund_reason(user_message),
                priority="medium",
                target_status=TicketStatus.PENDING_REVIEW.value,
                note="退款申请已提交，等待审核。",
                existing_ticket_id=existing_ticket_id,
            )
            return self._workflow_response(
                execution_status=ExecutionStatus.SUBMITTED.value,
                code=payload.get("code", "REFUND_REQUESTED"),
                message="您的退款申请已提交，请等待审核处理。",
                action=action,
                next_step="可在工单中查看退款进度。",
                ticket=ticket,
                result=payload.get("data", {}),
            )

        refund_message = payload.get("message", "退款失败")
        refund_message_cn = refund_message
        if "outside policy window" in refund_message:
            refund_message_cn = "该订单已超过退款时限，无法在线申请退款。"
        elif "already refunded" in refund_message:
            refund_message_cn = "该订单已退款，请勿重复申请。"

        ticket = await self._ensure_ticket(
            user_id=user_id,
            order_id=order_id,
            action=action,
            title=f"退款申请被拒绝：订单 {order_id}",
            description=refund_message_cn,
            priority="high",
            target_status=TicketStatus.REJECTED.value,
            note=refund_message_cn,
            existing_ticket_id=existing_ticket_id,
        )
        return self._workflow_response(
            execution_status=ExecutionStatus.FAILED.value,
            code=payload.get("code", "REFUND_FAILED"),
            message=refund_message_cn,
            action=action,
            next_step="如有疑问请联系我退人工客服。",
            ticket=ticket,
            result=payload.get("data", {}),
        )

    async def _handle_logistics_query(
        self,
        user_message: str,
        user_id: str,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        order_id = self._resolve_order_id(user_message, state)
        if not order_id:
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="ORDER_ID_REQUIRED",
                message="请先选择一个订单，我来帮您查询物流信息。",
                action="logistics_query",
                next_step="请在订单列表中选择一个订单。",
            )

        payload = await self._call_tool("logistics_query", {"order_id": order_id, "user_id": user_id})
        if not payload.get("success"):
            return self._workflow_response(
                execution_status=ExecutionStatus.FAILED.value,
                code=payload.get("code", "LOGISTICS_QUERY_FAILED"),
                message="抱歉，查询物流信息失败，请稍后重试。",
                action="logistics_query",
                next_step="请确认订单号是否正确。",
                result=payload.get("data", {}),
            )

        tracking_payload = await self._call_tool("logistics_tracking", {"order_id": order_id})
        result = {
            **payload.get("data", {}),
            "tracking": tracking_payload.get("data", {}).get("tracking", []),
        }

        logistics_status = result.get("status", "未知")
        express_company = result.get("express_company", "未知")
        tracking_number = result.get("tracking_number", "未知")

        LOGISTICS_STATUS_LABELS = {
            "pending": "待发货",
            "picked_up": "已取件",
            "in_transit": "运输中",
            "delivered": "已送达",
            "signed": "已签收",
            "exception": "异常",
        }
        logistics_status_cn = LOGISTICS_STATUS_LABELS.get(logistics_status, logistics_status)

        tracking_list = result.get("tracking", [])
        tracking_lines = []
        for item in tracking_list[-3:]:
            tracking_lines.append(
                f"- {item.get('timestamp', '')[:16]} | {item.get('location', '')} | {item.get('description', '')}"
            )

        message_lines = [
            f"快递公司：{express_company}",
            f"运单号：{tracking_number}",
            f"物流状态：{logistics_status_cn}",
        ]
        if tracking_lines:
            message_lines.append("最新动态：")
            message_lines.extend(tracking_lines)

        return self._workflow_response(
            execution_status=ExecutionStatus.EXECUTED.value,
            code="LOGISTICS_FOUND",
            message="\n".join(message_lines),
            action="logistics_query",
            next_step="如有其他问题，请随时告诉我。",
            result=result,
        )

    async def _handle_logistics_expedite(
        self,
        user_message: str,
        user_id: str,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = "logistics_expedite"
        order_id = self._resolve_order_id(user_message, state)
        if not order_id:
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="ORDER_ID_REQUIRED",
                message="请先选择一个订单，我来帮您催促发货。",
                action=action,
                next_step="请先在订单列表中选择要催发货的订单。",
            )

        open_ticket = await self._find_open_ticket(user_id=user_id, order_id=order_id, action=action)
        if open_ticket:
            return self._existing_ticket_response(
                ticket=open_ticket,
                action=action,
                default_message="该订单已有催促发货申请在处理中，请等待仓库处理。",
            )

        payload = await self._call_tool(
            "logistics_expedite",
            {"order_id": order_id, "user_id": user_id, "reason": user_message},
        )
        if not payload.get("success"):
            return self._workflow_response(
                execution_status=ExecutionStatus.FAILED.value,
                code=payload.get("code", "LOGISTICS_EXPEDITE_FAILED"),
                message="抱歉，催促发货失败，请稍后重试。",
                action=action,
                next_step="如有紧急需求，请联系客服热线。",
                result=payload.get("data", {}),
            )

        ticket = await self._get_ticket(payload.get("data", {}).get("ticket_id", ""), user_id)
        return self._workflow_response(
            execution_status=ExecutionStatus.SUBMITTED.value,
            code=payload.get("code", "LOGISTICS_EXPEDITE_CREATED"),
            message="已为您提交催促发货申请，仓库将加急处理，请耐心等待。",
            action=action,
            next_step="仓库正在加急处理，请耐心等待。",
            ticket=ticket,
            result=payload.get("data", {}),
        )

    def _handle_exchange_request(
        self,
        user_message: str,
        user_id: str,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        order_id = self._resolve_order_id(user_message, state)
        if not order_id:
            return self._workflow_response(
                execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
                code="ORDER_ID_REQUIRED",
                message="换货需要先确认订单，请先选择一个订单。",
                action="exchange_request",
                next_step="请先在订单列表中选择要换货的订单。",
            )
        return self._workflow_response(
            execution_status=ExecutionStatus.WAITING_USER_INPUT.value,
            code="EXCHANGE_NOT_SUPPORTED",
            message="抱歉，换货服务需要由人工客服协助处理。请联系客服热线：400-800-8888，或在此对话中描述您的换货需求（如换什么商品、原因等），我们会尽快为您处理。",
            action="exchange_request",
            next_step="如有其他问题，请随时告诉我。",
        )

    def _format_summary(self, workflow: dict[str, Any]) -> str:
        ticket_line = workflow.get("ticket_id") or "N/A"
        ticket_status = workflow.get("ticket_status_label") or workflow.get("ticket_status") or "N/A"
        return (
            f"Execution: {workflow.get('execution_status_label', workflow.get('execution_status', 'unknown'))}\n"
            f"Action: {workflow.get('action', '')}\n"
            f"Code: {workflow.get('code', '')}\n"
            f"Message: {workflow.get('message', '')}\n"
            f"Ticket: {ticket_line}\n"
            f"Ticket status: {ticket_status}\n"
            f"Next step: {workflow.get('next_step', 'None')}"
        )

    async def execute_action(
        self,
        action: str,
        user_message: str,
        user_id: str,
        existing_ticket_id: str = "",
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if action == "continuation" and state:
            last_action = state.get("last_action", "")
            if last_action and last_action != "continuation":
                action = last_action
            else:
                return self._workflow_response(
                    execution_status=ExecutionStatus.EXECUTED.value,
                    code="NO_PREVIOUS_ACTION",
                    message="抱歉，我没有找到您之前的话题。请直接告诉我您想做什么，比如查询订单、退款等。",
                    action="continuation",
                    next_step="请告诉我您的需求。",
                )
        if action == "ticket_query":
            return await self._handle_ticket_query(user_message, user_id)
        if action == "refund_apply":
            return await self._handle_refund(user_message, user_id, existing_ticket_id=existing_ticket_id, state=state)
        if action == "order_update_address":
            return await self._handle_address_change(user_message, user_id, existing_ticket_id=existing_ticket_id, state=state)
        if action == "logistics_query":
            return await self._handle_logistics_query(user_message, user_id, state=state)
        if action == "logistics_expedite":
            return await self._handle_logistics_expedite(user_message, user_id, state=state)
        if action == "exchange_request":
            return self._handle_exchange_request(user_message, user_id, state=state)
        return await self._handle_order_query(user_message, user_id, state)

    @trace_agent_call("ticket_handler_process")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state

        user_id = state.get("user_id", "anonymous")
        user_message = messages[-1].content
        action = state.get("execution_action", "order_query")
        workflow = await self.execute_action(action, user_message, user_id, state=state)

        return {
            **state,
            "workflow_result": workflow,
            "sub_results": {
                **state.get("sub_results", {}),
                "ticket_handler": self._format_summary(workflow),
            },
        }
