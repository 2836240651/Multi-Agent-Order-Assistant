"""Supervisor：StateGraph 主图 + 检查点管理。

W3 扩展：
- complexity≥60 或 intent in {refund,order_query,address_change,complex} → planner
- planner → critic → (plan_execute | planner(revise) | risk_review(escalate))
- plan_execute → END 或 risk_review（needs_review=True）
- interrupt_before=["risk_review"] 实现人审暂停

Checkpoint：
- APP_ENV=test → MemorySaver（内存，无需 DB）
- 生产    → AsyncPostgresSaver（需 PG_DSN_SYNC 含 langgraph schema）
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .critic import route_after_critic, run_critic
from .greeting_handler import run_greeting
from .intent_router import run_intent_router
from .knowledge_agent import run_knowledge_agent
from .plan_executor import run_plan_executor
from .planner import run_planner
from .risk_review import route_after_risk_review, run_risk_review
from .state import AgentState

logger = logging.getLogger(__name__)

# ── 路由函数 ──────────────────────────────────────────────────

_PLANNER_INTENTS = {"refund", "order_query", "address_change", "logistics_query", "ticket_create", "complex"}


def route_after_intent(state: AgentState) -> str:
    """intent_router 后的路由：简单 → knowledge/greeting；复杂 → planner。"""
    intent = state.get("intent") or "other"
    complexity = state.get("complexity") or 0
    if intent == "greeting":
        return "greeting"
    if intent in _PLANNER_INTENTS or complexity >= 60:
        return "planner"
    return "knowledge"


def route_after_plan_execute(state: AgentState) -> str:
    """plan_execute 后：若触发 needs_review → risk_review；否则结束。"""
    if state.get("needs_review"):
        return "risk_review"
    return "__end__"


# ── Checkpoint 工厂 ───────────────────────────────────────────

def _build_checkpointer():
    """根据环境构造检查点存储。"""
    app_env = os.getenv("APP_ENV", "dev")
    if app_env == "test":
        try:
            from langgraph.checkpoint.memory import MemorySaver
            return MemorySaver()
        except ImportError:
            return None

    # 生产：尝试 AsyncPostgresSaver
    pg_dsn = os.getenv("PG_DSN_SYNC", "")
    if not pg_dsn:
        logger.warning("PG_DSN_SYNC not set, checkpointer disabled")
        return None

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        # 同步初始化 schema；使用 psycopg 连接字符串
        import asyncio
        checkpointer = AsyncPostgresSaver.from_conn_string(pg_dsn)
        # setup() 需要事件循环；延迟到首次调用
        return checkpointer
    except ImportError:
        logger.warning("langgraph-checkpoint-postgres not installed, checkpointer disabled")
        return None
    except Exception as exc:
        logger.warning("checkpointer init failed: %s", exc)
        return None


# ── 图构建 ────────────────────────────────────────────────────

def build_graph(checkpointer=None) -> Any:
    """构建 W3 主图。返回已编译的 LangGraph CompiledStateGraph。"""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        logger.warning("langgraph not installed, using fallback runner")
        return _FallbackGraph()

    graph = StateGraph(AgentState)

    # 节点
    graph.add_node("intent_router", run_intent_router)
    graph.add_node("knowledge", run_knowledge_agent)
    graph.add_node("greeting", run_greeting)
    graph.add_node("planner", run_planner)
    graph.add_node("critic", run_critic)
    graph.add_node("plan_execute", run_plan_executor)
    graph.add_node("risk_review", run_risk_review)

    # 边
    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {"knowledge": "knowledge", "greeting": "greeting", "planner": "planner"},
    )
    graph.add_edge("knowledge", END)
    graph.add_edge("greeting", END)
    graph.add_edge("planner", "critic")
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"plan_execute": "plan_execute", "planner": "planner", "risk_review": "risk_review"},
    )
    graph.add_conditional_edges(
        "plan_execute",
        route_after_plan_execute,
        {"risk_review": "risk_review", "__end__": END},
    )
    graph.add_conditional_edges(
        "risk_review",
        route_after_risk_review,
        {"plan_execute": "plan_execute", "__end__": END},
    )

    compile_kwargs: dict[str, Any] = {
        "interrupt_before": ["risk_review"],
    }
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    return graph.compile(**compile_kwargs)


class _FallbackGraph:
    """无 langgraph 时的同步串行回退（仅用于测试 / 无依赖环境）。"""

    async def ainvoke(self, state: AgentState, config: dict | None = None) -> AgentState:
        merged = dict(state)
        merged.update(await run_intent_router(state) or {})
        nxt = route_after_intent(merged)  # type: ignore[arg-type]
        if nxt == "greeting":
            merged.update(await run_greeting(merged) or {})  # type: ignore[arg-type]
        elif nxt == "planner":
            merged.update(await run_planner(merged) or {})  # type: ignore[arg-type]
            merged.update(await run_critic(merged) or {})  # type: ignore[arg-type]
            merged.update(await run_plan_executor(merged) or {})  # type: ignore[arg-type]
        else:
            merged.update(await run_knowledge_agent(merged) or {})  # type: ignore[arg-type]
        return merged  # type: ignore[return-value]

    def get_graph(self):
        return _FallbackGraphMeta()


class _FallbackGraphMeta:
    def draw_mermaid(self) -> str:
        return "graph TD\n  A[intent_router] --> B[knowledge/greeting/planner]"


# ── 全局单例 ──────────────────────────────────────────────────

_compiled_graph: Any = None
_checkpointer: Any = None


def get_graph() -> Any:
    global _compiled_graph, _checkpointer
    if _compiled_graph is None:
        _checkpointer = _build_checkpointer()
        _compiled_graph = build_graph(checkpointer=_checkpointer)
    return _compiled_graph


def get_checkpointer() -> Any:
    get_graph()  # 确保初始化
    return _checkpointer


__all__ = ["build_graph", "get_graph", "get_checkpointer", "route_after_intent"]
