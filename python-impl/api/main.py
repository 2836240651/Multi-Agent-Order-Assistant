from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from agents.intent_router import IntentRouterAgent
from agents.supervisor import create_supervisor_graph
from agents.ticket_handler import TicketHandlerAgent
from governance.audit import AuditEvent, AuditLogger
from governance.review import ManualReviewManager
from governance.rollout import RolloutManager
from governance.ticket_status import (
    TICKET_ALLOWED_TRANSITIONS,
    TICKET_STATUS_DESCRIPTIONS,
    TICKET_STATUS_LABELS,
    allowed_ticket_transitions,
    enrich_ticket,
    is_terminal_ticket_status,
    ticket_next_step,
    ticket_status_label,
    normalize_ticket_status,
)
from governance.webhook import WebhookEventType, get_webhook_registry, emit_webhook
from governance.workflow_status import ExecutionStatus, execution_status_label
from llm_config import create_chat_model
from mcp.mcp_server import MCPToolServer, create_default_tools
from memory.long_term import LongTermMemory
from memory.short_term import ShortTermMemory
from memory.working_memory import WorkingMemory
from tracing.otel_config import AgentMetrics, RuntimeObservability, init_tracer

load_dotenv()

PII_RE = re.compile(r"(1[3-9]\d{9})|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})|(\d{17}[\dXx])")

from governance.websocket_manager import notification_manager, agent_manager

working_memory = WorkingMemory()
short_term_memory = ShortTermMemory(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
long_term_memory = LongTermMemory(index_path=os.getenv("FAISS_INDEX_PATH", "./vector_store/faiss_index"))
mcp_server = create_default_tools(MCPToolServer())
review_manager = ManualReviewManager()
rollout_manager = RolloutManager(
    {
        "baseline_v1": int(os.getenv("ROLLOUT_BASELINE_V1", "10")),
        "optimized_v2": int(os.getenv("ROLLOUT_OPTIMIZED_V2", "20")),
        "current_v3": int(os.getenv("ROLLOUT_CURRENT_V3", "70")),
    }
)
audit_logger = AuditLogger(os.path.join(os.getcwd(), "run", "audit_log.jsonl"))
metrics = AgentMetrics()
ops = RuntimeObservability()
graph = None
ticket_agent = TicketHandlerAgent(create_chat_model(temperature=0), mcp_server)
intent_router = IntentRouterAgent(create_chat_model(temperature=0))
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def _rebuild_runtime(reset_state: bool = False) -> None:
    global graph, mcp_server, review_manager, ticket_agent, intent_router
    if reset_state:
        mcp_server = create_default_tools(MCPToolServer())
        review_manager.reset()
        audit_logger.reset()
        ops.reset()
    ticket_agent = TicketHandlerAgent(create_chat_model(temperature=0), mcp_server)
    intent_router = IntentRouterAgent(create_chat_model(temperature=0))
    graph = create_supervisor_graph(
        working_memory=working_memory,
        short_term_memory=short_term_memory,
        long_term_memory=long_term_memory,
        mcp_server=mcp_server,
        review_manager=review_manager,
        audit_logger=audit_logger,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracer(
        service_name=os.getenv("OTEL_SERVICE_NAME", "smart-cs-multi-agent"),
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )
    _rebuild_runtime(reset_state=True)

    long_term_memory.add_document(
        content="Refund policy: users can request refund within 7 days after delivery.",
        source="refund_policy.md",
    )
    long_term_memory.add_document(
        content="Address can be changed only before package is shipped.",
        source="shipping_policy.md",
    )
    long_term_memory.add_document(
        content="Support channels: bot, phone hotline, and manual ticket review.",
        source="support_policy.md",
    )
    yield


app = FastAPI(
    title="RetailGuard Copilot API",
    description="Week4: observability, rollout control, and safe fallback execution",
    version="1.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    session_id: str | None = None
    rollout_variant: str | None = None
    order_id: str | None = None


class WorkflowResult(BaseModel):
    execution_status: str = ""
    execution_status_label: str = ""
    code: str = ""
    message: str = ""
    ticket_id: str = ""
    ticket_status: str = ""
    ticket_status_label: str = ""
    action: str = ""
    next_step: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class RiskResult(BaseModel):
    risk_level: str = ""
    requires_manual_review: bool = False
    reasons: list[str] = Field(default_factory=list)
    review_id: str = ""
    ticket_id: str = ""
    amount: float = 0.0


class ReleaseInfo(BaseModel):
    variant: str
    source: str
    degraded: bool = False
    fallback_reason: str = ""


class CostEstimate(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: str
    compliance_passed: bool
    execution_status: str = ""
    execution_status_label: str = ""
    ticket_id: str = ""
    ticket_status: str = ""
    ticket_status_label: str = ""
    action: str = ""
    next_step: str = ""
    workflow: WorkflowResult | None = None
    risk: RiskResult | None = None
    release: ReleaseInfo
    cost: CostEstimate
    processing_ms: float = 0.0
    trace: dict[str, Any] = Field(default_factory=dict)


class ReviewDecisionRequest(BaseModel):
    reviewer_note: str = ""


class TicketTransitionRequest(BaseModel):
    status: str
    note: str = ""


class RolloutUpdateRequest(BaseModel):
    baseline_v1: int = 10
    optimized_v2: int = 20
    current_v3: int = 70


class WebhookRegisterRequest(BaseModel):
    url: str
    events: list[str]
    secret: str = ""
    description: str = ""


def _build_initial_state(request: ChatRequest, session_id: str) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage

    entities = {}
    if request.order_id:
        entities["order_id"] = request.order_id

    last_context = working_memory.get_context(session_id)
    last_action = last_context.get("last_action", "")
    last_intent = last_context.get("last_intent", "")
    last_entities = last_context.get("entities", {})
    if last_entities and not entities.get("order_id"):
        entities.update(last_entities)

    return {
        "messages": [HumanMessage(content=request.message)],
        "user_id": request.user_id,
        "session_id": session_id,
        "intent": "",
        "execution_action": "",
        "entities": entities,
        "sub_results": {},
        "workflow_result": {},
        "risk_result": {},
        "compliance_passed": True,
        "final_response": "",
        "current_agent": "",
        "retry_count": 0,
        "last_user_message": request.message,
        "context_order_id": request.order_id or last_entities.get("order_id", ""),
        "last_action": last_action,
        "last_intent": last_intent,
    }


def _normalize_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    if not workflow:
        return {}
    execution_status = workflow.get("execution_status", "")
    return {
        **workflow,
        "execution_status_label": workflow.get("execution_status_label", execution_status_label(execution_status)),
        "ticket_status": workflow.get("ticket_status", ""),
        "ticket_status_label": workflow.get("ticket_status_label", ""),
    }


def _workflow_to_text(workflow: dict[str, Any]) -> str:
    workflow = _normalize_workflow(workflow)
    ticket_status_line = workflow.get("ticket_status_label") or workflow.get("ticket_status") or "N/A"
    return (
        f"[{workflow.get('execution_status_label', workflow.get('execution_status', 'unknown'))}] {workflow.get('message', '')}\n"
        f"Action: {workflow.get('action', '')}\n"
        f"Code: {workflow.get('code', '')}\n"
        f"Ticket: {workflow.get('ticket_id') or 'N/A'}\n"
        f"Ticket status: {ticket_status_line}\n"
        f"Next step: {workflow.get('next_step', 'None')}"
    )


def _workflow_to_user_text(workflow: dict[str, Any]) -> str:
    return workflow.get("message", "已处理您的请求。")


async def _queue_manual_review(
    *,
    session_id: str,
    user_id: str,
    action: str,
    message: str,
    order_id: str,
    reasons: list[str],
    risk_level: str,
    entities: dict[str, Any],
) -> dict[str, Any]:
    existing = review_manager.find_pending(order_id, action)
    if existing:
        return {
            "execution_status": ExecutionStatus.WAITING_MANUAL_REVIEW.value,
            "execution_status_label": execution_status_label(ExecutionStatus.WAITING_MANUAL_REVIEW.value),
            "code": "REVIEW_DUPLICATE",
            "message": "已有相同的待审核工单，请等待审核完成。",
            "ticket_id": existing.ticket_id,
            "ticket_status": "pending_manual_review",
            "ticket_status_label": TICKET_STATUS_LABELS["pending_manual_review"],
            "review_id": existing.review_id,
            "is_duplicate": True,
        }

    ticket_id = ""
    create_ticket = await mcp_server.call_tool(
        "ticket_create",
        {
            "title": f"Manual review required for {action}",
            "description": message,
            "priority": "high" if risk_level == "high" else "medium",
            "category": "manual_review",
            "order_id": order_id,
            "user_id": user_id,
            "action": action,
        },
    )
    ticket_payload = create_ticket.result if create_ticket.success else {"success": False, "data": {}}
    ticket_status = ""
    ticket_status_label = ""
    if ticket_payload.get("success"):
        ticket_id = ticket_payload["data"]["ticket_id"]
        update_ticket = await mcp_server.call_tool(
            "ticket_update",
            {
                "ticket_id": ticket_id,
                "status": "pending_manual_review",
                "note": "Queued by rollout safety gate.",
            },
        )
        update_payload = update_ticket.result if update_ticket.success else {"success": False, "data": {}}
        if update_payload.get("success"):
            ticket_status = update_payload["data"].get("ticket_status", "pending_manual_review")
            ticket_status_label = update_payload["data"].get("ticket_status_label", "")
        else:
            ticket_status = "pending_manual_review"
            ticket_status_label = TICKET_STATUS_LABELS.get(ticket_status, ticket_status)

    review = review_manager.create_review(
        session_id=session_id,
        user_id=user_id,
        action=action,
        risk_level=risk_level,
        reason="; ".join(reasons),
        ticket_id=ticket_id,
        order_id=order_id,
        workflow_snapshot={
            "action": action,
            "requested_message": message,
            "entities": entities,
        },
        evidence={"reasons": reasons, "source": "optimized_v2"},
    )
    audit_logger.append(
        AuditEvent(
            event_id=review.review_id,
            event_type="manual_review_requested",
            session_id=session_id,
            user_id=user_id,
            action=action,
            status="pending",
            details={"ticket_id": ticket_id, "risk_level": risk_level, "variant": "optimized_v2"},
            evidence={"reasons": reasons, "entities": entities},
        )
    )
    return {
        "execution_status": ExecutionStatus.WAITING_MANUAL_REVIEW.value,
        "execution_status_label": execution_status_label(ExecutionStatus.WAITING_MANUAL_REVIEW.value),
        "code": "REVIEW_REQUIRED",
        "message": "您的请求已提交，正在等待人工审核。",
        "ticket_id": ticket_id,
        "ticket_status": ticket_status or "pending_manual_review",
        "ticket_status_label": ticket_status_label or TICKET_STATUS_LABELS["pending_manual_review"],
        "action": action,
        "next_step": "请耐心等待，审核结果会在工单中更新。",
        "result": {},
        "risk": {
            "risk_level": risk_level,
            "requires_manual_review": True,
            "reasons": reasons,
            "review_id": review.review_id,
            "ticket_id": ticket_id,
            "amount": 0.0,
        },
    }


async def _run_baseline_v1(request: ChatRequest, session_id: str) -> dict[str, Any]:
    intent = await intent_router.classify(request.message)
    routing_state = {
        "entities": {**intent.entities, **({"order_id": request.order_id} if request.order_id else {})},
        "context_order_id": request.order_id or intent.entities.get("order_id", ""),
    }
    if intent.suggested_agent == "knowledge_rag":
        response = "This route uses the legacy rule engine. Please contact support for knowledge requests."
        return {
            "response": response,
            "intent": intent.suggested_agent,
            "compliance_passed": True,
            "workflow": {},
            "risk": {},
            "trace": {"route_mode": "baseline_v1", "entities": intent.entities},
        }

    workflow = await ticket_agent.execute_action(intent.execution_action, request.message, request.user_id, state=routing_state)
    audit_logger.append(
        AuditEvent(
            event_id=f"AU-{session_id}-baseline",
            event_type="workflow_completed",
            session_id=session_id,
            user_id=request.user_id,
            action=workflow.get("action", intent.execution_action),
            status=workflow.get("execution_status", "completed"),
            details={"variant": "baseline_v1", "ticket_id": workflow.get("ticket_id", "")},
            evidence={"workflow": workflow},
        )
    )
    return {
        "response": _workflow_to_user_text(workflow),
        "intent": intent.suggested_agent,
        "compliance_passed": True,
        "workflow": workflow,
        "risk": {},
        "trace": {"route_mode": "baseline_v1", "entities": intent.entities},
    }


async def _run_optimized_v2(request: ChatRequest, session_id: str) -> dict[str, Any]:
    intent = await intent_router.classify(request.message)
    routing_state = {
        "entities": {**intent.entities, **({"order_id": request.order_id} if request.order_id else {})},
        "context_order_id": request.order_id or intent.entities.get("order_id", ""),
    }
    if intent.suggested_agent == "knowledge_rag":
        return {
            "response": "Knowledge requests are routed to the documented FAQ path in optimized_v2.",
            "intent": intent.suggested_agent,
            "compliance_passed": True,
            "workflow": {},
            "risk": {},
            "trace": {"route_mode": "optimized_v2", "entities": intent.entities},
        }

    reasons: list[str] = []
    risk_level = "low"
    order_id = routing_state["entities"].get("order_id", "")
    amount = 0.0
    if order_id:
        order_lookup = await mcp_server.call_tool("order_query", {"order_id": order_id, "user_id": request.user_id})
        order_payload = order_lookup.result if order_lookup.success else {"success": False, "data": {}}
        if order_payload.get("success"):
            amount = float(order_payload["data"].get("amount", 0.0))

    if PII_RE.search(request.message):
        risk_level = "high"
        reasons.append("PII detected in user request.")
    if intent.execution_action == "refund_apply" and amount >= 1000:
        risk_level = "high"
        reasons.append(f"Refund amount {amount:.2f} exceeds auto-approval threshold.")
    if intent.execution_action == "order_update_address" and amount >= 5000:
        risk_level = "medium"
        reasons.append("Address update for higher-value order requires manual confirmation.")

    if reasons:
        queued = await _queue_manual_review(
            session_id=session_id,
            user_id=request.user_id,
            action=intent.execution_action,
            message=request.message,
            order_id=order_id,
            reasons=reasons,
            risk_level=risk_level,
            entities=intent.entities,
        )
        risk = queued.pop("risk")
        return {
            "response": _workflow_to_user_text(queued),
            "intent": intent.suggested_agent,
            "compliance_passed": True,
            "workflow": queued,
            "risk": risk,
            "trace": {"route_mode": "optimized_v2", "entities": intent.entities, "safety_gate": reasons},
        }

    workflow = await ticket_agent.execute_action(intent.execution_action, request.message, request.user_id, state=routing_state)
    audit_logger.append(
        AuditEvent(
            event_id=f"AU-{session_id}-optimized",
            event_type="workflow_completed",
            session_id=session_id,
            user_id=request.user_id,
            action=workflow.get("action", intent.execution_action),
            status=workflow.get("execution_status", "completed"),
            details={"variant": "optimized_v2", "ticket_id": workflow.get("ticket_id", "")},
            evidence={"workflow": workflow},
        )
    )
    return {
        "response": _workflow_to_user_text(workflow),
        "intent": intent.suggested_agent,
        "compliance_passed": True,
        "workflow": workflow,
        "risk": {},
        "trace": {"route_mode": "optimized_v2", "entities": intent.entities},
    }


async def _run_current_v3(request: ChatRequest, session_id: str) -> dict[str, Any]:
    if graph is None:
        raise HTTPException(status_code=503, detail="Service is starting.")

    result = await graph.ainvoke(
        _build_initial_state(request, session_id),
        config={"configurable": {"thread_id": session_id}},
    )
    final_response = result.get("final_response", "No response generated.")
    workflow = _normalize_workflow(result.get("workflow_result", {}) or {})
    risk = result.get("risk_result", {}) or {}
    intent_info = result.get("sub_results", {}).get("intent_router", {})
    trace = {
        "route_mode": "current_v3",
        "intent": intent_info.get("primary", ""),
        "execution_action": intent_info.get("execution_action", ""),
        "entities": intent_info.get("entities", {}),
        "risk_result": risk,
        "tool_calls": mcp_server.get_call_log(last_n=10),
    }
    return {
        "response": final_response,
        "intent": result.get("intent", "unknown"),
        "compliance_passed": result.get("compliance_passed", True),
        "workflow": workflow,
        "risk": risk,
        "trace": trace,
    }


async def _run_fallback_template(request: ChatRequest, session_id: str, reason: str) -> dict[str, Any]:
    intent = await intent_router.classify(request.message)
    action = intent.execution_action if intent.suggested_agent != "knowledge_rag" else "manual_support"
    workflow = {
        "execution_status": ExecutionStatus.DEGRADED_FALLBACK.value,
        "execution_status_label": execution_status_label(ExecutionStatus.DEGRADED_FALLBACK.value),
        "code": "RULE_FALLBACK_ACTIVATED",
        "message": "The primary workflow is temporarily unavailable. A safe fallback response was used.",
        "ticket_id": "",
        "ticket_status": "",
        "ticket_status_label": "",
        "action": action,
        "next_step": "Retry later or continue with manual support.",
        "result": {},
    }
    audit_logger.append(
        AuditEvent(
            event_id=f"AU-{session_id}-fallback",
            event_type="workflow_degraded",
            session_id=session_id,
            user_id=request.user_id,
            action=action,
            status="fallback_used",
            details={"reason": reason},
            evidence={"message": request.message},
        )
    )
    return {
        "response": _workflow_to_user_text(workflow),
        "intent": intent.suggested_agent,
        "compliance_passed": True,
        "workflow": workflow,
        "risk": {},
        "trace": {"route_mode": "fallback_template", "reason": reason, "entities": intent.entities},
    }


def _save_chat_message(message_id: str, user_id: str, order_id: str, session_id: str, role: str, content: str, created_at: str, intent: str, action: str):
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    last_error: Exception | None = None
    for _ in range(5):
        conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            conn.execute(
                '''
                INSERT INTO chat_messages (message_id, user_id, order_id, session_id, role, content, created_at, intent, action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (message_id, user_id, order_id, session_id, role, content, created_at, intent, action),
            )
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" not in str(exc).lower():
                raise
            time.sleep(0.2)
        finally:
            conn.close()
    if last_error is not None:
        raise last_error


async def _execute_variant(request: ChatRequest, session_id: str, variant: str) -> dict[str, Any]:
    if variant == "baseline_v1":
        return await _run_baseline_v1(request, session_id)
    if variant == "optimized_v2":
        return await _run_optimized_v2(request, session_id)
    return await _run_current_v3(request, session_id)


async def _run_chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    order_id = request.order_id or ""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    _save_chat_message(
        message_id=str(uuid.uuid4()),
        user_id=request.user_id,
        order_id=order_id,
        session_id=session_id,
        role="user",
        content=request.message,
        created_at=now,
        intent="",
        action="",
    )

    await short_term_memory.add_message(session_id, "user", request.message)
    started = time.perf_counter()
    release = rollout_manager.decide(user_id=request.user_id, requested_variant=request.rollout_variant)

    degraded = False
    fallback_reason = ""
    try:
        payload = await _execute_variant(request, session_id, release.selected_variant)
    except Exception as exc:
        degraded = True
        fallback_reason = str(exc)
        payload = await _run_fallback_template(request, session_id, fallback_reason)

    workflow = _normalize_workflow(payload.get("workflow", {}) or {})
    final_response = payload.get("response") or _workflow_to_user_text(workflow)
    risk = payload.get("risk", {}) or {}
    processing_ms = round((time.perf_counter() - started) * 1000, 2)
    await short_term_memory.add_message(session_id, "assistant", final_response)

    _save_chat_message(
        message_id=str(uuid.uuid4()),
        user_id=request.user_id,
        order_id=order_id,
        session_id=session_id,
        role="assistant",
        content=final_response,
        created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        intent=payload.get("intent", ""),
        action=workflow.get("action", "") or "",
    )

    prompt_tokens = ops.estimate_tokens(request.message)
    completion_tokens = ops.estimate_tokens(final_response)
    estimated_cost = ops.estimate_cost_usd(prompt_tokens, completion_tokens)
    success = workflow.get("execution_status", "") not in {
        ExecutionStatus.FAILED.value,
        ExecutionStatus.DEGRADED_FALLBACK.value,
    }
    error_code = workflow.get("code", "") if not success else ""
    ops.record_request(
        variant=release.selected_variant,
        action=workflow.get("action", ""),
        status=workflow.get("execution_status", ""),
        success=success,
        degraded=degraded,
        manual_review=bool(risk.get("requires_manual_review", False)),
        latency_ms=processing_ms,
        prompt_text=request.message,
        completion_text=final_response,
        error_code=error_code,
    )

    trace = payload.get("trace", {})
    trace["release"] = {
        "variant": release.selected_variant,
        "source": release.source,
        "degraded": degraded,
        "fallback_reason": fallback_reason,
    }

    return ChatResponse(
        response=final_response,
        session_id=session_id,
        intent=payload.get("intent", "unknown"),
        compliance_passed=payload.get("compliance_passed", True),
        execution_status=workflow.get("execution_status", ""),
        execution_status_label=workflow.get("execution_status_label", ""),
        ticket_id=workflow.get("ticket_id", "") or risk.get("ticket_id", ""),
        ticket_status=workflow.get("ticket_status", ""),
        ticket_status_label=workflow.get("ticket_status_label", ""),
        action=workflow.get("action", ""),
        next_step=workflow.get("next_step", ""),
        workflow=WorkflowResult(**workflow) if workflow else None,
        risk=RiskResult(**risk) if risk else None,
        release=ReleaseInfo(
            variant=release.selected_variant,
            source=release.source,
            degraded=degraded,
            fallback_reason=fallback_reason,
        ),
        cost=CostEstimate(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimated_cost,
        ),
        processing_ms=processing_ms,
        trace=trace,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    return await _run_chat(request)


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            request = ChatRequest(
                message=data.get("message", ""),
                user_id=data.get("user_id", "anonymous"),
                session_id=data.get("session_id", ""),
                order_id=data.get("order_id") or None,
            )
            response = await _run_chat(request)
            await websocket.send_json({
                "response": response.response,
                "session_id": response.session_id,
                "intent": response.intent,
                "execution_status": response.execution_status,
                "execution_status_label": response.execution_status_label,
                "ticket_id": response.ticket_id,
                "ticket_status": response.ticket_status,
                "ticket_status_label": response.ticket_status_label,
                "action": response.action,
                "next_step": response.next_step,
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass


@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    data = await websocket.receive_json()
    user_id = data.get("user_id")
    if not user_id:
        await websocket.close(code=4000, reason="user_id required")
        return

    await notification_manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await notification_manager.disconnect(websocket, user_id)


@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket):
    data = await websocket.receive_json()
    agent_id = data.get("agent_id")
    if not agent_id:
        await websocket.close(code=4001, reason="agent_id required")
        return

    await websocket.accept()
    await agent_manager.connect(websocket, agent_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await agent_manager.disconnect(websocket, agent_id)


@app.get("/api/agents/online")
async def list_online_agents():
    return {"agents": agent_manager.get_connected_users()}


@app.get("/api/history/{session_id}")
async def get_history(session_id: str):
    history = await short_term_memory.get_history(session_id)
    return {"session_id": session_id, "messages": history}


@app.get("/api/chat/history")
async def get_chat_history(user_id: str, order_id: str):
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT message_id, user_id, order_id, session_id, role, content, created_at, intent, action "
        "FROM chat_messages WHERE user_id = ? AND order_id = ? ORDER BY created_at ASC",
        (user_id, order_id),
    )
    rows = cursor.fetchall()
    conn.close()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@app.get("/api/tickets/state-machine")
async def get_ticket_state_machine():
    statuses = []
    for status, label in TICKET_STATUS_LABELS.items():
        statuses.append(
            {
                "status": status,
                "label": label,
                "description": TICKET_STATUS_DESCRIPTIONS.get(status, ""),
                "allowed_transitions": sorted(TICKET_ALLOWED_TRANSITIONS.get(status, [])),
            }
        )
    return {
        "statuses": statuses,
        "allowed_transitions": {status: sorted(targets) for status, targets in TICKET_ALLOWED_TRANSITIONS.items()},
    }


@app.get("/api/tickets")
async def list_tickets(
    user_id: str | None = None,
    order_id: str | None = None,
    action: str | None = None,
    status: str | None = None,
    include_closed: bool = True,
    limit: int = 50,
):
    result = await mcp_server.call_tool(
        "ticket_list",
        {
            "user_id": user_id or "",
            "order_id": order_id or "",
            "action": action or "",
            "status": status or "",
            "include_closed": include_closed,
            "limit": limit,
        },
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Ticket list failed."))
    return payload.get("data", {"items": [], "total": 0})


@app.get("/api/tickets/search")
async def search_tickets(
    user_id: str | None = None,
    order_id: str | None = None,
    status_in: str | None = None,
    priority_in: str | None = None,
    action_in: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    keyword: str | None = None,
    include_closed: bool = True,
    limit: int = 50,
    offset: int = 0,
):
    result = await mcp_server.call_tool(
        "ticket_search",
        {
            "user_id": user_id or "",
            "order_id": order_id or "",
            "status_in": [s.strip() for s in status_in.split(",")] if status_in else None,
            "priority_in": [p.strip() for p in priority_in.split(",")] if priority_in else None,
            "action_in": [a.strip() for a in action_in.split(",")] if action_in else None,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "keyword": keyword or "",
            "include_closed": include_closed,
            "limit": limit,
            "offset": offset,
        },
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Search failed."))
    return payload.get("data", {})


@app.get("/api/tickets/stats")
async def get_ticket_stats(include_closed: bool = True):
    result = await mcp_server.call_tool(
        "ticket_list",
        {"user_id": "", "order_id": "", "action": "", "status": "", "include_closed": include_closed, "limit": 1000},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Ticket stats failed."))
    items = payload.get("data", {}).get("items", [])
    by_status: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    open_count = 0
    for ticket in items:
        s = normalize_ticket_status(ticket.get("status"))
        by_status[s] = by_status.get(s, 0) + 1
        action = ticket.get("action", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
        priority = ticket.get("priority", "medium")
        by_priority[priority] = by_priority.get(priority, 0) + 1
        if not is_terminal_ticket_status(s):
            open_count += 1
    all_statuses = [
        {
            "status": status,
            "label": ticket_status_label(status),
            "count": by_status.get(status, 0),
            "is_terminal": is_terminal_ticket_status(status),
        }
        for status in TICKET_STATUS_LABELS
    ]
    return {
        "total": len(items),
        "open": open_count,
        "closed": len(items) - open_count,
        "by_status": by_status,
        "by_action": by_action,
        "by_priority": by_priority,
        "statuses": all_statuses,
    }


@app.get("/api/tickets/pending-summary")
async def get_ticket_pending_summary():
    result = await mcp_server.call_tool(
        "ticket_list",
        {"user_id": "", "order_id": "", "action": "", "status": "", "include_closed": False, "limit": 1000},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Pending summary failed."))
    items = payload.get("data", {}).get("items", [])
    pending_by_status: dict[str, list] = {}
    for ticket in items:
        s = normalize_ticket_status(ticket.get("status"))
        if s not in pending_by_status:
            pending_by_status[s] = []
        pending_by_status[s].append({
            "ticket_id": ticket.get("ticket_id"),
            "title": ticket.get("title", ""),
            "action": ticket.get("action", ""),
            "priority": ticket.get("priority", ""),
            "created_at": ticket.get("created_at", ""),
            "updated_at": ticket.get("updated_at", ""),
        })
    summary = [
        {
            "status": status,
            "label": ticket_status_label(status),
            "count": len(tickets),
            "tickets": tickets[:10],
        }
        for status, tickets in sorted(pending_by_status.items())
    ]
    total_pending = sum(s["count"] for s in summary)
    return {
        "total_pending": total_pending,
        "by_status": summary,
    }


@app.get("/api/tickets/overdue")
async def check_overdue_tickets_endpoint(batch_size: int = 50):
    result = await mcp_server.call_tool(
        "check_overdue_tickets",
        {"batch_size": batch_size},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Overdue check failed."))
    return payload.get("data", {})


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, user_id: str | None = None):
    result = await mcp_server.call_tool(
        "ticket_query",
        {"ticket_id": ticket_id, "user_id": user_id or "anonymous"},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        status_code = 404 if payload.get("code") == "TICKET_NOT_FOUND" else 400
        raise HTTPException(status_code=status_code, detail=payload.get("message", "Ticket query failed."))
    return payload.get("data", {})


@app.post("/api/tickets/{ticket_id}/transition")
async def transition_ticket(ticket_id: str, request: TicketTransitionRequest, user_id: str | None = None):
    normalized_status = normalize_ticket_status(request.status)
    current = await mcp_server.call_tool(
        "ticket_query",
        {"ticket_id": ticket_id, "user_id": user_id or "anonymous"},
    )
    current_payload = current.result if current.success else {"success": False, "message": current.error, "data": {}}
    if not current_payload.get("success"):
        status_code = 404 if current_payload.get("code") == "TICKET_NOT_FOUND" else 400
        raise HTTPException(status_code=status_code, detail=current_payload.get("message", "Ticket query failed."))

    updated = await mcp_server.call_tool(
        "ticket_update",
        {"ticket_id": ticket_id, "status": normalized_status, "note": request.note},
    )
    updated_payload = updated.result if updated.success else {"success": False, "message": updated.error, "data": {}}
    if not updated_payload.get("success"):
        raise HTTPException(status_code=400, detail=updated_payload.get("message", "Ticket transition failed."))

    ticket_query = await mcp_server.call_tool("ticket_query", {"ticket_id": ticket_id, "user_id": user_id or "anonymous"})
    if ticket_query.success and ticket_query.result:
        ticket_data = ticket_query.result.get("data", {})
        ticket_user_id = ticket_data.get("user_id")
        if ticket_user_id:
            await notification_manager.send_to_user(
                ticket_user_id,
                {
                    "type": "ticket_update",
                    "ticket_id": ticket_id,
                    "status": normalized_status,
                    "message": f"您的工单状态已更新为：{ticket_status_label(normalized_status)}",
                    "order_id": ticket_data.get("order_id"),
                },
            )

    return updated_payload.get("data", {})


@app.get("/api/tickets/{ticket_id}/allowed-transitions")
async def get_ticket_allowed_transitions(ticket_id: str, user_id: str | None = None):
    result = await mcp_server.call_tool(
        "ticket_query",
        {"ticket_id": ticket_id, "user_id": user_id or "anonymous"},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        status_code = 404 if payload.get("code") == "TICKET_NOT_FOUND" else 400
        raise HTTPException(status_code=status_code, detail=payload.get("message", "Ticket query failed."))
    ticket = payload.get("data", {})
    current_status = normalize_ticket_status(ticket.get("status"))
    allowed = allowed_ticket_transitions(current_status)
    return {
        "ticket_id": ticket_id,
        "current_status": current_status,
        "current_status_label": ticket_status_label(current_status),
        "allowed_transitions": allowed,
        "allowed_transitions_with_labels": [
            {"status": s, "label": ticket_status_label(s), "is_terminal": is_terminal_ticket_status(s)}
            for s in allowed
        ],
    }


@app.get("/api/tickets/{ticket_id}/timeline")
async def get_ticket_timeline(ticket_id: str, user_id: str | None = None):
    result = await mcp_server.call_tool(
        "ticket_query",
        {"ticket_id": ticket_id, "user_id": user_id or "anonymous"},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        status_code = 404 if payload.get("code") == "TICKET_NOT_FOUND" else 400
        raise HTTPException(status_code=status_code, detail=payload.get("message", "Ticket query failed."))
    ticket = payload.get("data", {})
    history = ticket.get("history") or []
    timeline = []
    for i, entry in enumerate(history):
        entry_status = normalize_ticket_status(entry.get("status"))
        timeline.append({
            "step": i + 1,
            "status": entry_status,
            "status_label": ticket_status_label(entry_status),
            "note": entry.get("note", ""),
            "timestamp": entry.get("timestamp", ""),
            "next_step": entry.get("next_step") or ticket_next_step(entry_status),
            "is_current": i == len(history) - 1,
        })
    current_status = normalize_ticket_status(ticket.get("status"))
    return {
        "ticket_id": ticket_id,
        "current_status": current_status,
        "current_status_label": ticket_status_label(current_status),
        "total_steps": len(timeline),
        "timeline": timeline,
    }


@app.post("/api/webhooks")
async def register_webhook(request: WebhookRegisterRequest):
    registry = get_webhook_registry()
    webhook = await registry.register(
        url=request.url,
        events=request.events,
        secret=request.secret,
        description=request.description,
    )
    return {
        "webhook_id": webhook.webhook_id,
        "url": webhook.url,
        "events": webhook.events,
        "secret": webhook.secret,
        "description": webhook.description,
        "is_active": webhook.is_active,
        "created_at": webhook.created_at,
    }


@app.get("/api/webhooks")
async def list_webhooks():
    registry = get_webhook_registry()
    webhooks = await registry.list_all()
    return {
        "webhooks": [
            {
                "webhook_id": w.webhook_id,
                "url": w.url,
                "events": w.events,
                "description": w.description,
                "is_active": w.is_active,
                "created_at": w.created_at,
                "delivery_stats": w.delivery_stats,
            }
            for w in webhooks
        ],
        "total": len(webhooks),
    }


@app.get("/api/webhooks/event-types")
async def list_webhook_event_types():
    from governance.webhook import WEBHOOK_EVENT_LABELS, WebhookEventType
    return {
        "event_types": [
            {"event": e.value, "label": WEBHOOK_EVENT_LABELS[e]}
            for e in WebhookEventType
        ]
    }


@app.get("/api/webhooks/{webhook_id}")
async def get_webhook(webhook_id: str):
    registry = get_webhook_registry()
    webhook = await registry.get(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    return {
        "webhook_id": webhook.webhook_id,
        "url": webhook.url,
        "events": webhook.events,
        "secret": webhook.secret,
        "description": webhook.description,
        "is_active": webhook.is_active,
        "created_at": webhook.created_at,
        "delivery_stats": webhook.delivery_stats,
    }


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    registry = get_webhook_registry()
    deleted = await registry.unregister(webhook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    return {"message": "Webhook deleted."}


@app.get("/api/webhooks/{webhook_id}/deliveries")
async def get_webhook_deliveries(webhook_id: str, limit: int = 20):
    registry = get_webhook_registry()
    webhook = await registry.get(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    deliveries = await registry.deliveries(webhook_id, limit=limit)
    return {
        "webhook_id": webhook_id,
        "deliveries": [
            {
                "delivery_id": d.delivery_id,
                "event_type": d.event_type,
                "status": d.status,
                "attempts": d.attempts,
                "last_attempt_at": d.last_attempt_at,
                "response_status": d.response_status,
                "error": d.error,
                "created_at": d.created_at,
            }
            for d in deliveries
        ],
    }


@app.post("/api/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    registry = get_webhook_registry()
    try:
        delivery = await registry.test(webhook_id)
        return {
            "delivery_id": delivery.delivery_id,
            "status": delivery.status,
            "attempts": delivery.attempts,
            "response_status": delivery.response_status,
            "response_body": delivery.response_body,
            "error": delivery.error,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.patch("/api/webhooks/{webhook_id}/toggle")
async def toggle_webhook(webhook_id: str, is_active: bool):
    registry = get_webhook_registry()
    webhook = await registry.get(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    webhook.is_active = is_active
    return {"webhook_id": webhook_id, "is_active": webhook.is_active}


@app.post("/api/tickets/{ticket_id}/rate")
async def rate_ticket(ticket_id: str, rating: int, user_id: str, rating_comment: str = ""):
    result = await mcp_server.call_tool(
        "ticket_rate",
        {"ticket_id": ticket_id, "user_id": user_id, "rating": rating, "rating_comment": rating_comment},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Rating failed."))
    return payload.get("data", {})


@app.post("/api/chat/{session_id}/mark-read")
async def mark_messages_read(session_id: str, user_id: str, message_ids: list[str] | None = None):
    result = await mcp_server.call_tool(
        "chat_messages_mark_read",
        {"session_id": session_id, "user_id": user_id, "message_ids": message_ids},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Mark read failed."))
    return payload.get("data", {})


@app.get("/api/chat/{session_id}/unread-count")
async def get_unread_count(session_id: str, user_id: str):
    result = await mcp_server.call_tool(
        "chat_unread_count",
        {"session_id": session_id, "user_id": user_id},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Unread count failed."))
    return payload.get("data", {})


@app.get("/api/audit/operational-logs")
async def query_operational_logs(
    operator_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
):
    result = await mcp_server.call_tool(
        "operational_log_query",
        {
            "operator_id": operator_id or "",
            "target_type": target_type or "",
            "target_id": target_id or "",
            "action": action or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "limit": limit,
        },
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        raise HTTPException(status_code=400, detail=payload.get("message", "Log query failed."))
    return payload.get("data", {})


@app.post("/api/tickets/{ticket_id}/assign")
async def assign_ticket(ticket_id: str, assigned_to: str, note: str = ""):
    result = await mcp_server.call_tool(
        "ticket_assign",
        {"ticket_id": ticket_id, "assigned_to": assigned_to, "note": note},
    )
    payload = result.result if result.success else {"success": False, "message": result.error, "data": {}}
    if not payload.get("success"):
        code = payload.get("code", "")
        status_code = 404 if code == "TICKET_NOT_FOUND" else 400
        raise HTTPException(status_code=status_code, detail=payload.get("message", "Assign failed."))
    return payload.get("data", {})


@app.get("/api/tools")
async def list_tools():
    return {"tools": mcp_server.list_tools()}


@app.get("/api/orders")
async def list_orders(user_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0):
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT order_id, user_id, product_name, amount, status, address, can_update_address, refund_eligible FROM orders WHERE 1=1"
    params = []
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY rowid DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM orders" + (" WHERE user_id = ?" if user_id else "") + (" AND status = ?" if status else ""), [u for u in [user_id, status] if u])
    total = cursor.fetchone()[0]
    conn.close()
    
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@app.get("/api/users")
async def list_users(vip_level: str | None = None, limit: int = 50, offset: int = 0):
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT user_id, username, email, phone, registration_date, vip_level, total_spent FROM users WHERE 1=1"
    params = []
    if vip_level:
        query += " AND vip_level = ?"
        params.append(vip_level)
    query += " ORDER BY total_spent DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM users" + (" WHERE vip_level = ?" if vip_level else ""), [vip_level] if vip_level else [])
    total = cursor.fetchone()[0]
    conn.close()
    
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    cursor.execute(
        "SELECT order_id, product_name, amount, status, address, order_date, can_update_address, refund_eligible "
        "FROM orders WHERE user_id = ? ORDER BY order_date DESC LIMIT 10",
        (user_id,),
    )
    orders = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
    order_count = cursor.fetchone()[0]
    
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user": dict(user),
        "orders": [dict(r) for r in orders],
        "order_count": order_count
    }


@app.post("/api/tools/call")
async def call_tool(request: dict[str, Any]):
    result = await mcp_server.call_tool(
        name=request.get("name", ""),
        arguments=request.get("arguments", {}),
    )
    return {
        "success": result.success,
        "result": result.result,
        "error": result.error,
        "duration_ms": result.duration_ms,
    }


@app.get("/api/metrics")
async def get_metrics():
    return {
        "agent_metrics": metrics.get_summary(),
        "runtime_observability": ops.get_summary(),
        "tool_call_log": mcp_server.get_call_log(last_n=20),
        "pending_manual_reviews": len(review_manager.list_pending()),
        "rollout": rollout_manager.summary(),
    }


@app.get("/api/ops/overview")
async def get_ops_overview():
    return {
        "runtime": ops.get_summary(),
        "rollout": rollout_manager.summary(),
        "audit_recent": audit_logger.list_events(limit=10),
    }


@app.get("/api/ops/rollout")
async def get_rollout_config():
    return rollout_manager.summary()


@app.post("/api/ops/rollout")
async def update_rollout_config(request: RolloutUpdateRequest):
    weights = rollout_manager.update_weights(request.model_dump())
    return {"status": "ok", "weights": weights, "summary": rollout_manager.summary()}


@app.get("/api/demo/run_case")
async def run_demo_case(
    case: str = "order_success",
    user_id: str = "anonymous",
    rollout_variant: str | None = None,
):
    _rebuild_runtime(reset_state=True)
    cases = {
        "order_success": "帮我查一下订单 ORD-20260113-0001 的状态",
        "refund_success": "我要申请退款，订单号 ORD-20260113-0001，因为不想要了",
        "refund_high_risk": "我要申请退款，订单号 ORD-20260402-0002，因为不想要了",
        "refund_failed": "我要退款，订单 ORD-20260208-0002，因为用了两个月了",
        "address_success": "帮我修改地址，订单 ORD-20260113-0001 地址: Shanghai Minhang District 99",
        "address_failed": "帮我改地址，订单 ORD-20260330-0008 地址: Beijing Chaoyang District 66",
        "pii_review": "我要退款，订单号 ORD-20260113-0001，我的手机号是 13812345678",
        "legacy_rollout": "帮我查一下订单 ORD-20260113-0001",
    }
    if case not in cases:
        raise HTTPException(status_code=400, detail=f"Unknown case: {case}")
    request = ChatRequest(
        message=cases[case],
        user_id=user_id,
        session_id=str(uuid.uuid4()),
        rollout_variant=rollout_variant,
    )
    return await _run_chat(request)


@app.post("/api/demo/reset")
async def reset_demo_data():
    _rebuild_runtime(reset_state=True)
    _use_mysql_reset = os.getenv("MYSQL_HOST") is not None
    if _use_mysql_reset:
        try:
            from mcp.init_mysql import init_database
            init_database(drop_existing=False)
        except Exception:
            pass
    return {"status": "ok", "message": "Demo runtime has been reset."}


@app.get("/api/reviews/pending")
async def list_pending_reviews():
    items = review_manager.list_pending()
    for item in items:
        if item.get("action") == "refund_apply" and item.get("order_id"):
            order_check = await mcp_server.call_tool(
                "order_query",
                {"order_id": item["order_id"], "user_id": item.get("user_id", "anonymous")}
            )
            if order_check.success and order_check.result:
                order_data = order_check.result.get("data", {})
                item["order_info"] = {
                    "refund_eligible": order_data.get("refund_eligible", False),
                    "refund_deadline": order_data.get("refund_deadline", ""),
                    "deliver_date": order_data.get("deliver_date", ""),
                    "amount": order_data.get("amount", 0),
                }
            else:
                item["order_info"] = {"refund_eligible": None, "error": str(order_check.error) if order_check.error else "无法查询订单"}
    return {"items": items}


@app.post("/api/reviews/{review_id}/approve")
async def approve_review(review_id: str, request: ReviewDecisionRequest):
    item = review_manager.get(review_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found.")
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="Review item is already resolved.")

    if item.action == "refund_apply" and item.order_id:
        order_check = await mcp_server.call_tool("order_query", {"order_id": item.order_id, "user_id": item.user_id})
        if order_check.success and order_check.result:
            order_data = order_check.result.get("data", {})
            if not order_data.get("refund_eligible"):
                refund_deadline = order_data.get("refund_deadline", "订单送达后7天内")
                raise HTTPException(
                    status_code=400,
                    detail=f"⚠️ 风险提示：该订单已超过退款时限（{refund_deadline}），审批通过后退款将失败。建议拒绝此申请。"
                )

    workflow = await ticket_agent.execute_action(
        item.action,
        item.workflow_snapshot.get("requested_message", ""),
        item.user_id,
        existing_ticket_id=item.ticket_id,
        state={
            "entities": item.workflow_snapshot.get("entities", {}),
            "context_order_id": item.order_id,
        },
    )
    review_manager.resolve(review_id, "approved", request.reviewer_note)
    audit_logger.append(
        AuditEvent(
            event_id=review_id,
            event_type="manual_review_resolved",
            session_id=item.session_id,
            user_id=item.user_id,
            action=item.action,
            status="approved",
            details={"ticket_id": item.ticket_id, "reviewer_note": request.reviewer_note},
            evidence={"workflow": workflow},
        )
    )
    if item.user_id:
        await notification_manager.send_to_user(
            item.user_id,
            {
                "type": "ticket_update",
                "ticket_id": item.ticket_id,
                "action": item.action,
                "status": "approved",
                "message": f"您的{item.action}申请已通过审核，正在执行中。",
                "order_id": item.order_id,
            },
        )
    return {"review_id": review_id, "resolution": "approved", "workflow": workflow}


@app.post("/api/reviews/{review_id}/reject")
async def reject_review(review_id: str, request: ReviewDecisionRequest):
    item = review_manager.get(review_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found.")
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="Review item is already resolved.")

    review_manager.resolve(review_id, "rejected", request.reviewer_note)
    if item.ticket_id:
        await mcp_server.call_tool(
            "ticket_update",
            {
                "ticket_id": item.ticket_id,
                "status": "rejected",
                "note": request.reviewer_note or "Rejected by manual reviewer.",
            },
        )
        await notification_manager.send_to_user(
            item.user_id,
            {
                "type": "ticket_update",
                "ticket_id": item.ticket_id,
                "action": item.action,
                "status": "rejected",
                "message": f"您的{item.action}申请已被拒绝：{request.reviewer_note or '审核未通过'}",
                "order_id": item.order_id,
            },
        )
    audit_logger.append(
        AuditEvent(
            event_id=review_id,
            event_type="manual_review_resolved",
            session_id=item.session_id,
            user_id=item.user_id,
            action=item.action,
            status="rejected",
            details={"ticket_id": item.ticket_id, "reviewer_note": request.reviewer_note},
            evidence=item.evidence,
        )
    )
    return {"review_id": review_id, "resolution": "rejected"}


class RegisterRequest(BaseModel):
    user_id: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
async def register(request: RegisterRequest):
    import hashlib
    from datetime import datetime
    
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Check if user_id exists in orders
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (request.user_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="用户ID不存在，请输入正确的用户ID")
    
    # Check if email already registered
    cursor.execute("SELECT email FROM users_auth WHERE email = ?", (request.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="该邮箱已被注册")
    
    # Check if user_id already registered
    cursor.execute("SELECT user_id FROM users_auth WHERE user_id = ?", (request.user_id,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="该用户ID已绑定其他账号")
    
    # Hash password and create auth record
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute(
        "INSERT INTO users_auth (user_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (request.user_id, request.email, password_hash, now)
    )
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "注册成功", "user_id": request.user_id}


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    import hashlib
    from datetime import datetime
    
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    cursor.execute(
        "SELECT u.*, ua.email FROM users u LEFT JOIN users_auth ua ON u.user_id = ua.user_id WHERE ua.email = ? AND ua.password_hash = ?",
        (request.email, password_hash)
    )
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    
    # Update last login
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE users_auth SET last_login = ? WHERE email = ?", (now, request.email))
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": "登录成功",
        "user": dict(user)
    }


class StaffLoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/staff/login")
async def staff_login(request: StaffLoginRequest):
    staff_username = os.getenv("STAFF_USERNAME", "admin")
    staff_password = os.getenv("STAFF_PASSWORD", "admin123")
    
    if request.username == staff_username and request.password == staff_password:
        token = f"staff_{uuid.uuid4().hex[:16]}"
        return {
            "success": True,
            "message": "登录成功",
            "token": token,
            "staff": {
                "username": request.username,
                "role": "staff"
            }
        }
    
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@app.get("/api/auth/me")
async def get_current_user(user_id: str | None = None):
    db_path = Path(__file__).resolve().parents[1] / "mcp" / "commerce.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return {"user": dict(user)}


@app.get("/api/audit/logs")
async def list_audit_logs(event_type: str | None = None, action: str | None = None, limit: int = 100):
    return {"items": audit_logger.list_events(event_type=event_type, action=action, limit=limit)}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.3.0"}


@app.get("/", include_in_schema=False)
async def root():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        {
            "message": "RetailGuard Copilot API is running.",
            "docs": "/docs",
            "frontend_built": False,
        }
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_assets(full_path: str):
    if not FRONTEND_DIST.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not found.")

    asset_path = (FRONTEND_DIST / full_path).resolve()
    frontend_root = FRONTEND_DIST.resolve()
    if frontend_root not in asset_path.parents and asset_path != frontend_root:
        raise HTTPException(status_code=404, detail="Asset not found.")

    if asset_path.exists() and asset_path.is_file():
        return FileResponse(asset_path)

    return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
