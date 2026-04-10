from __future__ import annotations

import re
from typing import Any

from langchain_openai import ChatOpenAI

from governance.audit import AuditEvent, AuditLogger
from governance.review import ManualReviewManager
from governance.ticket_status import TicketStatus, ticket_status_label
from governance.workflow_status import ExecutionStatus, execution_status_label
from mcp.mcp_server import MCPToolServer
from tracing.otel_config import trace_agent_call


PII_PATTERNS = {
    "phone": r"1[3-9]\d{9}",
    "id_card": r"\d{17}[\dXx]",
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
}


class RiskReviewAgent:
    def __init__(
        self,
        llm: ChatOpenAI,
        mcp_server: MCPToolServer,
        review_manager: ManualReviewManager,
        audit_logger: AuditLogger,
    ):
        self.llm = llm
        self.mcp_server = mcp_server
        self.review_manager = review_manager
        self.audit_logger = audit_logger

    def _contains_pii(self, text: str) -> list[str]:
        detected = []
        for label, pattern in PII_PATTERNS.items():
            if re.search(pattern, text):
                detected.append(label)
        return detected

    async def _extract_amount(self, order_id: str, user_id: str) -> float:
        if not order_id:
            return 0.0
        lookup = await self.mcp_server.call_tool("order_query", {"order_id": order_id, "user_id": user_id})
        payload = lookup.result if lookup.success else {}
        if payload.get("success"):
            return float(payload["data"].get("amount", 0.0))
        return 0.0

    @trace_agent_call("risk_review")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        user_message = state.get("last_user_message", "")
        user_id = state.get("user_id", "anonymous")
        session_id = state.get("session_id", "")
        action = state.get("execution_action", "")
        order_id = state.get("entities", {}).get("order_id", "")
        amount = await self._extract_amount(order_id, user_id)
        risk_check = await self.mcp_server.call_tool(
            "risk_check",
            {"user_id": user_id, "action": action, "amount": amount},
        )
        risk_payload = risk_check.result if risk_check.success else {"success": False, "data": {}}
        risk_level = risk_payload.get("data", {}).get("risk_level", "low")
        requires_manual_review = risk_payload.get("data", {}).get("requires_manual_review", False)
        reasons: list[str] = []

        workflow_result = state.get("workflow_result", {})
        failed_code = workflow_result.get("code", "")
        business_rule_failed = (
            workflow_result.get("execution_status") == ExecutionStatus.FAILED.value
            and failed_code in ("REFUND_NOT_ELIGIBLE", "ORDER_FORBIDDEN", "ORDER_QUERY_FAILED")
        )

        pii_hits = self._contains_pii(user_message)
        if pii_hits:
            requires_manual_review = True
            risk_level = "high"
            reasons.append(f"检测到用户请求中包含PII信息: {', '.join(pii_hits)}")

        if business_rule_failed:
            requires_manual_review = False
            risk_level = "low"
            reasons.append(f"业务规则判定失败: {workflow_result.get('message', failed_code)}")
        elif action == "refund_apply" and amount >= 1000:
            requires_manual_review = True
            risk_level = "high"
            reasons.append(f"退款金额 {amount:.2f} 元超过自动审批阈值")

        if action == "order_update_address" and amount >= 5000:
            requires_manual_review = True
            if risk_level == "low":
                risk_level = "medium"
            reasons.append("高价值订单的地址变更需要人工确认")

        review_id = ""
        ticket_id = ""
        if requires_manual_review:
            existing = self.review_manager.find_pending(order_id, action)
            if existing:
                review_id = existing.review_id
                ticket_id = existing.ticket_id
            else:
                create_ticket = await self.mcp_server.call_tool(
                    "ticket_create",
                    {
                        "title": f"Manual review required for {action}",
                        "description": user_message,
                        "priority": "high" if risk_level == "high" else "medium",
                        "category": "manual_review",
                        "order_id": order_id,
                        "user_id": user_id,
                        "action": action,
                    },
                )
                ticket_payload = create_ticket.result if create_ticket.success else {"success": False, "data": {}}
                if ticket_payload.get("success"):
                    ticket_id = ticket_payload["data"]["ticket_id"]
                    await self.mcp_server.call_tool(
                        "ticket_update",
                        {
                            "ticket_id": ticket_id,
                            "status": "pending_manual_review",
                            "note": "Queued for human approval before execution.",
                        },
                    )
                review = self.review_manager.create_review(
                    session_id=session_id,
                    user_id=user_id,
                    action=action,
                    risk_level=risk_level,
                    reason="; ".join(reasons) or "风险引擎请求人工审核",
                    ticket_id=ticket_id,
                    order_id=order_id,
                    workflow_snapshot={
                        "action": action,
                        "requested_message": user_message,
                        "entities": state.get("entities", {}),
                    },
                    evidence={
                        "risk_check": risk_payload.get("data", {}),
                        "user_message": user_message,
                    },
                )
                review_id = review.review_id
                self.audit_logger.append(
                    AuditEvent(
                        event_id=review.review_id,
                        event_type="manual_review_requested",
                        session_id=session_id,
                        user_id=user_id,
                        action=action,
                        status="pending",
                        details={"ticket_id": ticket_id, "risk_level": risk_level},
                        evidence=review.evidence,
                    )
                )

        summary = (
            f"Risk Review: level={risk_level}, manual_review={requires_manual_review}, "
            f"review_id={review_id or 'N/A'}, ticket_id={ticket_id or 'N/A'}"
        )

        if requires_manual_review:
            updated_workflow_result = {
                "execution_status": ExecutionStatus.WAITING_MANUAL_REVIEW.value,
                "execution_status_label": execution_status_label(ExecutionStatus.WAITING_MANUAL_REVIEW.value),
                "code": "REVIEW_REQUIRED",
                "message": "您的请求已提交，正在等待人工审核。",
                "ticket_id": ticket_id,
                "ticket_status": TicketStatus.PENDING_MANUAL_REVIEW.value,
                "ticket_status_label": ticket_status_label(TicketStatus.PENDING_MANUAL_REVIEW.value),
                "action": action,
                "next_step": "请耐心等待，审核结果会在工单中更新。",
                "result": {},
            }
        else:
            updated_workflow_result = workflow_result

        return {
            **state,
            "workflow_result": updated_workflow_result,
            "risk_result": {
                "risk_level": risk_level,
                "requires_manual_review": requires_manual_review,
                "reasons": reasons,
                "review_id": review_id,
                "ticket_id": ticket_id,
                "amount": amount,
            },
            "sub_results": {
                **state.get("sub_results", {}),
                "risk_review": summary,
            },
        }
