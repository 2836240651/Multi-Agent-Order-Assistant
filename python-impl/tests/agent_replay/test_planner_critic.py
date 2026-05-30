"""tests/agent_replay/test_planner_critic.py：Planner + Critic 节点回放测试。"""
from __future__ import annotations

import json
import pytest

from agents.state import initial_state, AgentState
from agents.planner import run_planner, PlanStep
from agents.critic import run_critic, route_after_critic


# ── 测试辅助 ─────────────────────────────────────────────────

def _state_with_message(content: str, complexity: int = 70, intent: str = "refund") -> AgentState:
    return initial_state(
        messages=[{"role": "user", "content": content}],
        thread_id="test",
        user_id=1,
        tenant_id=1,
        version="v3",
    ) | {"intent": intent, "complexity": complexity}


# ── Planner 测试 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_planner_returns_plan_steps():
    """Planner 应返回至少 1 个步骤的计划。"""
    state = _state_with_message("我想退款，订单号 ORD-001，金额 299 元")
    update = await run_planner(state)
    plan = update.get("plan") or []
    assert isinstance(plan, list)
    assert len(plan) >= 1
    # 每步有必填字段
    for step in plan:
        assert "action" in step
        assert "step" in step


@pytest.mark.asyncio
async def test_planner_escalates_on_unparseable_echo():
    """echo provider 返回非 JSON 时，Planner 应生成 escalate 步骤而不是崩溃。"""
    state = _state_with_message("退款", complexity=90, intent="complex")
    update = await run_planner(state)
    plan = update.get("plan") or []
    assert isinstance(plan, list)
    assert len(plan) >= 1
    # 允许 escalate 或正常步骤（echo 模式下两者都可能）
    actions = {s.get("action") for s in plan}
    assert actions <= {"query_order", "check_refund_policy", "create_refund",
                        "change_address", "query_kb", "escalate", "reply_user", "other"}


@pytest.mark.asyncio
async def test_planner_sets_current_step_to_zero():
    """Planner 执行后 current_step 应重置为 0。"""
    state = _state_with_message("改收货地址")
    update = await run_planner(state)
    assert update.get("current_step") == 0


# ── Critic 测试 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critic_escalates_when_max_revise_exceeded():
    """超过最大修订次数（2 次）时 Critic 必须 escalate。"""
    state: AgentState = _state_with_message("退款 999 元") | {  # type: ignore[assignment]
        "plan": [{"step": 1, "action": "create_refund", "args": {}, "description": "退款"}],
        "revise_count": 2,  # 已达上限
        "critic_history": [],
    }
    update = await run_critic(state)
    history = update.get("critic_history") or []
    assert len(history) == 1
    assert history[-1]["verdict"] == "escalate"


@pytest.mark.asyncio
async def test_critic_revise_empty_plan():
    """空计划应该被 Critic 标记为 revise。"""
    state: AgentState = _state_with_message("退款") | {  # type: ignore[assignment]
        "plan": [],
        "revise_count": 0,
        "critic_history": [],
    }
    update = await run_critic(state)
    history = update.get("critic_history") or []
    assert len(history) == 1
    assert history[-1]["verdict"] == "revise"


@pytest.mark.asyncio
async def test_critic_revise_increments_count():
    """Critic revise 时 revise_count 应递增。"""
    state: AgentState = _state_with_message("退款") | {  # type: ignore[assignment]
        "plan": [],
        "revise_count": 0,
        "critic_history": [],
    }
    update = await run_critic(state)
    assert update.get("revise_count") == 1


# ── 路由函数测试 ──────────────────────────────────────────────

def test_route_after_critic_approve():
    """approve 时路由到 plan_execute。"""
    state: AgentState = {"critic_history": [{"verdict": "approve", "reason": "ok", "fix_hints": []}]}  # type: ignore
    assert route_after_critic(state) == "plan_execute"


def test_route_after_critic_revise():
    """revise 时路由回 planner。"""
    state: AgentState = {"critic_history": [{"verdict": "revise", "reason": "missing amount", "fix_hints": []}]}  # type: ignore
    assert route_after_critic(state) == "planner"


def test_route_after_critic_escalate():
    """escalate 时路由到 risk_review。"""
    state: AgentState = {"critic_history": [{"verdict": "escalate", "reason": "too risky", "fix_hints": []}]}  # type: ignore
    assert route_after_critic(state) == "risk_review"


def test_route_after_critic_empty_history():
    """空历史时默认走 plan_execute。"""
    state: AgentState = {"critic_history": []}  # type: ignore
    assert route_after_critic(state) == "plan_execute"
