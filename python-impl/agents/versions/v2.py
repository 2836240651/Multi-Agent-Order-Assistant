"""agents/versions/v2.py：V2 — 单 Agent + LLM 意图 + 规则风控。

特点（相较 V1 改进）：
- 意图识别调 LLM（更准确）
- 添加规则层风控（无 LLM 评分，仅 rules + features）
- 无 Planner/Critic 多步规划
"""
from __future__ import annotations

import logging
from typing import Any

from agents.state import AgentState

logger = logging.getLogger(__name__)


async def _v2_risk_lite(state: AgentState) -> AgentState:
    """V2 轻量风控：仅规则 + 特征，无 LLM 评分。"""
    from risk.rules import evaluate_rules
    from risk.features import evaluate_features

    plan = state.get("plan") or []
    has_refund = any(s.get("action") == "create_refund" for s in plan)
    if not has_refund:
        return AgentState(needs_review=False)  # type: ignore[return-value]

    msgs = state.get("messages") or []
    last_user = next((m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"), "")
    refund_ctx = {"amount": 0, "description": last_user, "days_since_delivery": 0,
                  "user_refund_count_30d": 0, "is_duplicate_refund": False, "cross_tenant_anomaly": False}

    rules_r = evaluate_rules(refund_ctx)
    feats_r = evaluate_features(refund_ctx)
    score = rules_r.score * 0.6 + feats_r.score * 0.4
    needs_review = score >= 60 or not rules_r.passed
    return AgentState(needs_review=needs_review)  # type: ignore[return-value]


def build_v2(checkpointer=None) -> Any:
    """V2 图：intent_router → knowledge → (risk_lite →) END / greeting → END。"""
    try:
        from langgraph.graph import END, START, StateGraph
        from agents.greeting_handler import run_greeting
        from agents.intent_router import run_intent_router
        from agents.knowledge_agent import run_knowledge_agent
    except ImportError:
        return None

    _REFUND_INTENTS = {"refund", "address_change"}

    def route_after_intent(state: AgentState) -> str:
        intent = state.get("intent") or "knowledge"
        if intent == "greeting":
            return "greeting"
        return "knowledge"

    def route_after_knowledge(state: AgentState) -> str:
        intent = state.get("intent") or "knowledge"
        if intent in _REFUND_INTENTS:
            return "risk_lite"
        return "__end__"

    graph = StateGraph(AgentState)
    graph.add_node("intent_router", run_intent_router)
    graph.add_node("knowledge", run_knowledge_agent)
    graph.add_node("greeting", run_greeting)
    graph.add_node("risk_lite", _v2_risk_lite)
    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges("intent_router", route_after_intent,
                                {"greeting": "greeting", "knowledge": "knowledge"})
    graph.add_conditional_edges("knowledge", route_after_knowledge,
                                {"risk_lite": "risk_lite", "__end__": END})
    graph.add_edge("risk_lite", END)
    graph.add_edge("greeting", END)
    kwargs = {}
    if checkpointer:
        kwargs["checkpointer"] = checkpointer
    return graph.compile(**kwargs)


__all__ = ["build_v2"]
