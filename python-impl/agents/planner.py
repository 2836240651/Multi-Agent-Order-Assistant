"""agents/planner.py：将复杂请求分解为 PlanStep 列表。

设计.md §6.3 W3 落地。
调用 LLM profile=heavy 输出 JSON；解析失败最多重试 2 次；全部失败 → escalate。
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from llm import call_llm
from agents.state import AgentState
from tracing.observe import observe

logger = logging.getLogger(__name__)

# ── 数据模型 ──────────────────────────────────────────────────

class PlanStep(BaseModel):
    """单步执行计划。"""
    step: int = Field(ge=1, description="步骤序号，从 1 开始")
    action: Literal[
        "query_order", "check_refund_policy", "create_refund",
        "change_address", "query_kb", "escalate", "reply_user", "other"
    ]
    tool: str | None = None
    args: dict = Field(default_factory=dict)
    description: str = Field(max_length=200)


class PlanResult(BaseModel):
    """LLM 返回的完整计划。"""
    steps: list[PlanStep] = Field(min_length=1, max_length=10)
    summary: str = Field(max_length=200)


# ── Prompt ────────────────────────────────────────────────────

_SYSTEM = """你是电商售后 Planner。根据用户请求，拆分为 1-5 个可执行步骤的 JSON 计划。

可用 action 类型：
- query_order：查订单状态/物流
- check_refund_policy：查退款政策（天数、金额限制）
- create_refund：发起退款申请
- change_address：修改收货地址
- query_kb：知识库查询（非业务操作）
- escalate：转人工（风险/超阈值/无法处理）
- reply_user：直接回复用户（最终步骤）
- other：其他

输出纯 JSON，格式：
{
  "steps": [
    {"step": 1, "action": "...", "tool": null, "args": {}, "description": "简短说明（20字内）"},
    ...
  ],
  "summary": "整体计划一句话描述（30字内）"
}

不要输出任何其他内容。"""

_USER_TMPL = """用户消息：{message}
意图：{intent}（复杂度 {complexity}/100）
历史步骤（如有）：{history}"""

_MAX_RETRIES = 2


# ── 核心逻辑 ──────────────────────────────────────────────────

def _last_user_message(state: AgentState) -> str:
    for m in reversed(state.get("messages") or []):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _safe_parse_plan(text: str) -> PlanResult | None:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return PlanResult.model_validate(data)
    except Exception as exc:
        logger.debug("plan parse error: %s", exc)
        return None


def _escalate_plan() -> PlanResult:
    return PlanResult(
        steps=[PlanStep(step=1, action="escalate", description="自动升级：Planner 多次失败")],
        summary="无法生成计划，转人工处理",
    )


@observe(name="planner.run", capture_input=False)
async def run_planner(state: AgentState) -> AgentState:
    """节点函数：生成执行计划写回 state["plan"]。"""
    text = _last_user_message(state)
    intent = state.get("intent") or "complex"
    complexity = state.get("complexity") or 60
    history_str = json.dumps(state.get("plan") or [], ensure_ascii=False)[:300]

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": _USER_TMPL.format(
                message=text, intent=intent, complexity=complexity, history=history_str
            ),
        },
    ]

    plan: PlanResult | None = None
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            result = await call_llm(profile="heavy", messages=messages, stream=False)
            plan = _safe_parse_plan(result.text)  # type: ignore[union-attr]
            if plan is not None:
                break
            logger.warning("planner attempt %d: parse failed, retrying", attempt)
        except Exception as exc:
            logger.warning("planner attempt %d error: %s", attempt, exc)

    if plan is None:
        logger.error("planner failed after %d attempts, escalating", _MAX_RETRIES + 1)
        plan = _escalate_plan()

    plan_dicts = [s.model_dump() for s in plan.steps]
    logger.info("plan generated: %d steps — %s", len(plan_dicts), plan.summary)

    return AgentState(plan=plan_dicts, current_step=0)  # type: ignore[return-value]


__all__ = ["PlanStep", "PlanResult", "run_planner"]
