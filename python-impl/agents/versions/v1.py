"""agents/versions/v1.py：V1 — 单 Agent + 关键词查询（基线版本）。

特点：
- 无 Planner/Critic，直接 knowledge_agent 处理所有请求
- 意图识别只做关键词匹配，不调 LLM
- 无风控层，无多步规划
"""
from __future__ import annotations

import logging
from typing import Any

from agents.state import AgentState

logger = logging.getLogger(__name__)


async def _v1_intent(state: AgentState) -> AgentState:
    """关键词规则意图（不调 LLM，零成本）。"""
    import re
    msgs = state.get("messages") or []
    text = next((m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"), "")
    patterns = [
        ("greeting", re.compile(r"^(你好|您好|hi|hello|在吗)$", re.IGNORECASE)),
        ("refund", re.compile(r"退款|退货")),
        ("knowledge", re.compile(r".")),  # fallback
    ]
    intent = "knowledge"
    for name, pat in patterns:
        if pat.search(text):
            intent = name
            break
    return AgentState(intent=intent, complexity=0)  # type: ignore[return-value]


def build_v1(checkpointer=None) -> Any:
    """V1 图：START → v1_intent → knowledge/greeting → END。"""
    try:
        from langgraph.graph import END, START, StateGraph
        from agents.greeting_handler import run_greeting
        from agents.knowledge_agent import run_knowledge_agent
    except ImportError:
        logger.warning("langgraph not available for v1")
        return None

    graph = StateGraph(AgentState)
    graph.add_node("v1_intent", _v1_intent)
    graph.add_node("knowledge", run_knowledge_agent)
    graph.add_node("greeting", run_greeting)
    graph.add_edge(START, "v1_intent")
    graph.add_conditional_edges(
        "v1_intent",
        lambda s: "greeting" if s.get("intent") == "greeting" else "knowledge",
        {"greeting": "greeting", "knowledge": "knowledge"},
    )
    graph.add_edge("knowledge", END)
    graph.add_edge("greeting", END)
    kwargs = {}
    if checkpointer:
        kwargs["checkpointer"] = checkpointer
    return graph.compile(**kwargs)


__all__ = ["build_v1"]
