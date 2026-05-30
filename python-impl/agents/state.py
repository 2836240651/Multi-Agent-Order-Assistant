"""AgentState：LangGraph 图的统一状态对象。

设计.md §6.2。W1 仅启用必要字段；后续周扩展。
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Sequence, TypedDict


def _append_messages(existing: list, new: list) -> list:  # 简化版 reducer
    return (existing or []) + (new or [])


class AgentState(TypedDict, total=False):
    """LangGraph state。所有字段都有默认（避免 KeyError）。"""

    # 输入
    messages: Annotated[list[dict[str, Any]], _append_messages]
    thread_id: str
    user_id: int | None
    tenant_id: int | None
    version: Literal["v1", "v2", "v3"]

    # 路由
    intent: str | None
    complexity: int  # 0-100

    # 知识
    citations: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    answer: str | None

    # 工单（W3+）
    ticket_no: str | None
    refund_no: str | None

    # Planner（W3+）
    plan: list[dict[str, Any]]  # list[PlanStep.model_dump()]
    current_step: int  # 当前执行到第几步

    # 风控（W4+）
    risk_decision: dict[str, Any] | None
    needs_review: bool

    # Critic（W3+）
    critic_history: list[dict[str, Any]]
    revise_count: int

    # 控制
    interrupt_reason: str | None
    error: dict[str, Any] | None

    # 模型 & 成本
    model_calls: list[dict[str, Any]]
    total_cost: float


def initial_state(
    *,
    messages: Sequence[dict[str, Any]],
    thread_id: str,
    user_id: int | None,
    tenant_id: int | None,
    version: str = "v3",
) -> AgentState:
    """构造初始 state。"""
    return AgentState(
        messages=list(messages),
        thread_id=thread_id,
        user_id=user_id,
        tenant_id=tenant_id,
        version=version,  # type: ignore[arg-type]
        intent=None,
        complexity=0,
        citations=[],
        retrieved_chunks=[],
        answer=None,
        ticket_no=None,
        refund_no=None,
        plan=[],
        current_step=0,
        risk_decision=None,
        needs_review=False,
        critic_history=[],
        revise_count=0,
        interrupt_reason=None,
        error=None,
        model_calls=[],
        total_cost=0.0,
    )


__all__ = ["AgentState", "initial_state"]
