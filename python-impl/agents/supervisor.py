from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.compliance_checker import ComplianceCheckerAgent
from agents.greeting_handler import GreetingHandlerAgent
from agents.intent_router import IntentRouterAgent
from agents.knowledge_rag import KnowledgeRAGAgent
from agents.risk_review import RiskReviewAgent
from agents.ticket_handler import TicketHandlerAgent
from governance.audit import AuditEvent, AuditLogger
from governance.review import ManualReviewManager
from llm_config import create_chat_model
from mcp.mcp_server import MCPToolServer
from memory.long_term import LongTermMemory
from memory.short_term import ShortTermMemory
from memory.working_memory import WorkingMemory
from tracing.otel_config import trace_agent_call


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    intent: str
    execution_action: str
    entities: dict[str, str]
    sub_results: dict[str, Any]
    workflow_result: dict[str, Any]
    risk_result: dict[str, Any]
    compliance_passed: bool
    final_response: str
    current_agent: str
    retry_count: int
    last_user_message: str
    context_order_id: str
    last_action: str
    last_intent: str


class SupervisorNode:
    def __init__(self, working_memory: WorkingMemory, audit_logger: AuditLogger):
        self.working_memory = working_memory
        self.audit_logger = audit_logger

    @trace_agent_call("supervisor_route")
    async def after_intent_route(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "knowledge_rag")
        session_id = state.get("session_id", "default")
        entities = state.get("entities", {})
        self.working_memory.update(
            session_id,
            {
                "last_intent": intent,
                "last_action": state.get("execution_action", ""),
                "entities": entities,
            },
        )
        return {
            **state,
            "current_agent": "supervisor",
        }

    @trace_agent_call("supervisor_synthesize")
    async def synthesize_response(self, state: AgentState) -> AgentState:
        workflow = state.get("workflow_result", {})
        risk_result = state.get("risk_result", {})
        compliance_passed = state.get("compliance_passed", True)
        sub_results = state.get("sub_results", {})
        session_id = state.get("session_id", "")
        user_id = state.get("user_id", "")
        action = workflow.get("action", "") or state.get("execution_action", "")

        if not compliance_passed:
            final_response = "您的请求因合规检查未通过已被拦截，已转由人工处理。"
        elif risk_result.get("requires_manual_review"):
            final_response = workflow.get("message", "您的请求已提交，正在等待人工审核。")
        elif workflow:
            final_response = workflow.get("message", "已处理您的请求。")
        elif state.get("final_response"):
            final_response = state.get("final_response")
        else:
            final_response = sub_results.get("knowledge_rag", "No actionable result was produced.")

        self.audit_logger.append(
            AuditEvent(
                event_id=f"AU-{session_id}-{action or 'knowledge'}",
                event_type="workflow_completed",
                session_id=session_id,
                user_id=user_id,
                action=action or "knowledge",
                status=workflow.get("execution_status", "review_pending" if risk_result.get("requires_manual_review") else "completed"),
                details={
                    "ticket_id": workflow.get("ticket_id", "") or risk_result.get("ticket_id", ""),
                    "review_id": risk_result.get("review_id", ""),
                    "risk_level": risk_result.get("risk_level", "low"),
                    "compliance_passed": compliance_passed,
                },
                evidence={
                    "workflow": workflow,
                    "risk_result": risk_result,
                    "compliance": sub_results.get("compliance", {}),
                },
            )
        )

        return {
            **state,
            "final_response": final_response,
            "messages": [AIMessage(content=final_response)],
        }


def route_to_execution(state: AgentState) -> str:
    intent = state.get("intent", "knowledge_rag")
    if intent == "ticket_handler":
        return "ticket_handler"
    if intent == "greeting_handler":
        return "greeting_handler"
    return "knowledge_rag"


def route_after_risk(state: AgentState) -> str:
    if state.get("risk_result", {}).get("requires_manual_review"):
        return "compliance_check"
    return "synthesize"


def create_supervisor_graph(
    llm: ChatOpenAI | None = None,
    working_memory: WorkingMemory | None = None,
    short_term_memory: ShortTermMemory | None = None,
    long_term_memory: LongTermMemory | None = None,
    mcp_server: MCPToolServer | None = None,
    review_manager: ManualReviewManager | None = None,
    audit_logger: AuditLogger | None = None,
    enable_checkpointing: bool = True,
):
    if llm is None:
        llm = create_chat_model(temperature=0)
    if working_memory is None:
        working_memory = WorkingMemory()
    if mcp_server is None:
        raise ValueError("mcp_server is required for execution tools.")
    if review_manager is None:
        raise ValueError("review_manager is required for risk review.")
    if audit_logger is None:
        raise ValueError("audit_logger is required for audit logging.")

    supervisor = SupervisorNode(working_memory, audit_logger)
    intent_router = IntentRouterAgent(llm)
    knowledge_agent = KnowledgeRAGAgent(llm, long_term_memory)
    ticket_agent = TicketHandlerAgent(llm, mcp_server=mcp_server)
    risk_agent = RiskReviewAgent(llm, mcp_server, review_manager, audit_logger)
    compliance_agent = ComplianceCheckerAgent(llm)
    greeting_agent = GreetingHandlerAgent()

    graph = StateGraph(AgentState)
    graph.add_node("intent_router", intent_router.process)  # type: ignore[arg-type]
    graph.add_node("supervisor_route", supervisor.after_intent_route)  # type: ignore[arg-type]
    graph.add_node("knowledge_rag", knowledge_agent.process)  # type: ignore[arg-type]
    graph.add_node("ticket_handler", ticket_agent.process)  # type: ignore[arg-type]
    graph.add_node("risk_review", risk_agent.process)  # type: ignore[arg-type]
    graph.add_node("compliance_check", compliance_agent.process)  # type: ignore[arg-type]
    graph.add_node("greeting_handler", greeting_agent.process)  # type: ignore[arg-type]
    graph.add_node("synthesize", supervisor.synthesize_response)  # type: ignore[arg-type]

    graph.set_entry_point("intent_router")
    graph.add_edge("intent_router", "supervisor_route")
    graph.add_conditional_edges(
        "supervisor_route",
        route_to_execution,
        {
            "ticket_handler": "ticket_handler",
            "knowledge_rag": "knowledge_rag",
            "greeting_handler": "greeting_handler",
        },
    )
    graph.add_edge("ticket_handler", "risk_review")
    graph.add_edge("knowledge_rag", "risk_review")
    graph.add_conditional_edges(
        "risk_review",
        route_after_risk,
        {
            "compliance_check": "compliance_check",
            "synthesize": "synthesize",
        },
    )
    graph.add_edge("compliance_check", "synthesize")
    graph.add_edge("greeting_handler", "synthesize")
    graph.add_edge("synthesize", END)

    checkpointer = MemorySaver() if enable_checkpointing else None
    compiled_graph = graph.compile(checkpointer=checkpointer)
    return compiled_graph  # type: ignore[return-value]
