"""agents/critic.py：审查 Planner 计划的质量与合规性。

设计.md §6.3 W3 落地。
检查维度：金额一致性 / 政策合规 / 字段完整 / 与历史不矛盾。
verdict：approve（通过）/ revise（退回修改）/ escalate（转人工）。
revise 最多回退 2 次（由 supervisor 计数），超出则 escalate。
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from llm import call_llm
from agents.state import AgentState
from tracing.observe import observe

logger = logging.getLogger(__name__)

# ── 数据模型 ──────────────────────────────────────────────────

class CriticResult(BaseModel):
    verdict: Literal["approve", "revise", "escalate"]
    reason: str = Field(max_length=300)
    fix_hints: list[str] = Field(default_factory=list, max_length=5)


# ── Prompt ────────────────────────────────────────────────────

_SYSTEM = """你是电商售后 Critic，负责审查执行计划的质量。

检查维度（发现任意问题则给出 revise 或 escalate）：
1. 金额一致性：退款金额与订单实收是否匹配
2. 政策合规：退款/地址变更是否在允许时间窗口内
3. 字段完整：关键 args（order_no/amount/address 等）是否缺失
4. 与历史不矛盾：步骤是否与已知状态冲突

verdict 说明：
- approve：计划正确可执行
- revise：发现问题，提供 fix_hints 供 Planner 修正
- escalate：风险过高或多次 revise 仍有问题，需人工介入

输出纯 JSON：
{"verdict": "approve|revise|escalate", "reason": "...", "fix_hints": ["hint1", ...]}"""

_USER_TMPL = """用户请求：{message}
当前计划：
{plan}

历史修订次数：{revise_count}
已知上下文：{context}"""

_MAX_REVISE = 2


# ── 辅助 ──────────────────────────────────────────────────────

def _last_user_message(state: AgentState) -> str:
    for m in reversed(state.get("messages") or []):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _safe_parse_critic(text: str) -> CriticResult | None:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return CriticResult.model_validate(data)
    except Exception as exc:
        logger.debug("critic parse error: %s", exc)
        return None


def _build_context(state: AgentState) -> str:
    """从 state 提取已知上下文（票号、风控、历史修订）供 Critic 参考。"""
    ctx: dict = {}
    if state.get("ticket_no"):
        ctx["ticket_no"] = state["ticket_no"]
    if state.get("risk_decision"):
        ctx["risk"] = state["risk_decision"]
    if state.get("critic_history"):
        ctx["critic_history"] = state["critic_history"][-3:]
    return json.dumps(ctx, ensure_ascii=False)[:500] if ctx else "无"


# ── 节点函数 ──────────────────────────────────────────────────

@observe(name="critic.run", capture_input=False)
async def run_critic(state: AgentState) -> AgentState:
    """节点函数：审查计划并写回 critic_history + revise_count。"""
    revise_count = state.get("revise_count") or 0

    # 超出最大修订次数 → 强制 escalate
    if revise_count >= _MAX_REVISE:
        result = CriticResult(
            verdict="escalate",
            reason=f"已修订 {revise_count} 次仍未通过，转人工",
            fix_hints=[],
        )
        return _write_critic_result(state, result)

    plan = state.get("plan") or []
    if not plan:
        result = CriticResult(verdict="revise", reason="计划为空", fix_hints=["需要至少一个执行步骤"])
        return _write_critic_result(state, result)

    message = _last_user_message(state)
    plan_str = json.dumps(plan, ensure_ascii=False, indent=2)[:1500]
    context_str = _build_context(state)

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": _USER_TMPL.format(
                message=message,
                plan=plan_str,
                revise_count=revise_count,
                context=context_str,
            ),
        },
    ]

    critic: CriticResult | None = None
    try:
        llm_result = await call_llm(profile="heavy", messages=messages, stream=False)
        critic = _safe_parse_critic(llm_result.text)  # type: ignore[union-attr]
    except Exception as exc:
        logger.warning("critic LLM failed: %s", exc)

    if critic is None:
        # LLM 失败时 → 宽松 approve，避免死循环
        critic = CriticResult(verdict="approve", reason="[critic_fallback] LLM 不可用，默认放行")

    logger.info("critic verdict=%s reason=%s", critic.verdict, critic.reason[:80])
    return _write_critic_result(state, critic)


def _write_critic_result(state: AgentState, result: CriticResult) -> AgentState:
    history = list(state.get("critic_history") or [])
    history.append(result.model_dump())
    revise_count = state.get("revise_count") or 0
    if result.verdict == "revise":
        revise_count += 1
    return AgentState(  # type: ignore[return-value]
        critic_history=history,
        revise_count=revise_count,
    )


# ── 路由条件（供 supervisor 使用） ────────────────────────────

def route_after_critic(state: AgentState) -> str:
    """返回下一节点名称：plan_execute / planner（revise） / risk_review（escalate）。"""
    history = state.get("critic_history") or []
    if not history:
        return "plan_execute"
    last = history[-1]
    verdict = last.get("verdict", "approve")
    if verdict == "approve":
        return "plan_execute"
    if verdict == "revise":
        return "planner"
    return "risk_review"  # escalate


__all__ = ["CriticResult", "run_critic", "route_after_critic"]
