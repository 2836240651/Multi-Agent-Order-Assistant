"""agents/plan_executor.py：按 PlanStep 列表依次调用工具/Agent。

W3 简化实现：
- query_order / check_refund_policy / create_refund / change_address → mock 返回占位
- query_kb → 转发给 knowledge_agent
- escalate → 置 needs_review=True
- reply_user → 把已有 answer 写回
"""
from __future__ import annotations

import logging
from typing import Any

from agents.state import AgentState
from tracing.observe import observe

logger = logging.getLogger(__name__)


def _last_user_message(state: AgentState) -> str:
    for m in reversed(state.get("messages") or []):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


async def _execute_step(step: dict[str, Any], state: AgentState) -> dict[str, Any]:
    """执行单步，返回写回 state 的 patch dict。"""
    action = step.get("action", "other")
    args = step.get("args") or {}

    if action == "query_kb":
        from agents.knowledge_agent import run_knowledge_agent
        update = await run_knowledge_agent(state)
        return {"answer": update.get("answer"), "citations": update.get("citations", [])}

    if action == "escalate":
        return {
            "needs_review": True,
            "interrupt_reason": step.get("description") or "plan escalate",
        }

    if action == "reply_user":
        return {}  # answer 已由前置步骤写入

    # 工单类操作：W3 mock 占位，W5 接真实工单服务
    if action == "query_order":
        order_no = args.get("order_no", "（未提供订单号）")
        return {"answer": f"订单 {order_no} 状态查询已提交（W3 mock）。"}

    if action == "check_refund_policy":
        return {"answer": "退款政策：收货后 7 天内可申请无理由退款（W3 mock）。"}

    if action == "create_refund":
        amount = args.get("amount", "?")
        return {
            "answer": f"退款申请已提交，金额 ¥{amount}，预计 3-5 个工作日到账（W3 mock）。",
            "refund_no": f"RFD-MOCK-{hash(str(args)) % 100000:05d}",
        }

    if action == "change_address":
        new_addr = args.get("address", "（未提供地址）")
        return {"answer": f"收货地址已更新为：{new_addr}（W3 mock）。"}

    return {}


@observe(name="plan_executor.run", capture_input=False)
async def run_plan_executor(state: AgentState) -> AgentState:
    """节点函数：遍历执行 plan 中所有步骤，合并写回 state。"""
    plan = state.get("plan") or []
    if not plan:
        return AgentState(answer="没有可执行的计划步骤。")  # type: ignore[return-value]

    merged: dict[str, Any] = {}
    for step in plan:
        step_desc = step.get("description", step.get("action", "?"))
        logger.info("executing step %s: %s", step.get("step"), step_desc)
        patch = await _execute_step(step, AgentState(**{**state, **merged}))
        merged.update({k: v for k, v in patch.items() if v is not None})
        if merged.get("needs_review"):
            break  # escalate → 停止后续步骤，等待人审

    return AgentState(**merged)  # type: ignore[return-value]


__all__ = ["run_plan_executor"]
