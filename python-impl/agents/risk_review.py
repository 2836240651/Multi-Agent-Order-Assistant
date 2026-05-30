"""agents/risk_review.py：风控人审节点（W4 薄壳，调 risk.evaluate()）。

W3 中是 stub，W4 接三层融合风控引擎。
- 调用 risk.evaluate(refund, tenant_id) 获取 RiskDecision
- decision=reject → interrupt 阻断
- decision=review → 触发 interrupt（等人审）
- decision=pass  → 直接放行继续
"""
from __future__ import annotations

import logging
import re
from typing import Any

from agents.state import AgentState
from tracing.observe import observe

logger = logging.getLogger(__name__)


def _extract_refund_context(state: AgentState) -> dict[str, Any]:
    """从 plan + messages 中提取退款上下文供 risk.evaluate() 使用。"""
    plan = state.get("plan") or []
    msgs = state.get("messages") or []
    last_user = next((m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"), "")

    # 从 plan 步骤 args 中提取金额等
    refund_args: dict[str, Any] = {}
    for step in plan:
        if step.get("action") == "create_refund":
            refund_args.update(step.get("args") or {})

    amount = float(refund_args.get("amount", 0) or 0)
    if amount <= 0:
        m = re.search(r"(\d+(?:\.\d+)?)\s*元", last_user)
        if m:
            amount = float(m.group(1))
        else:
            m2 = re.search(r"退(?:款)?\s*(\d{2,5})", last_user)
            if m2:
                amount = float(m2.group(1))

    return {
        "amount": amount,
        "reason": refund_args.get("reason", "") or last_user[:80],
        "description": last_user,
        "product_name": refund_args.get("product_name", ""),
        "days_since_delivery": int(refund_args.get("days_since_delivery", 0)),
        "days_since_order": int(refund_args.get("days_since_order", 0)),
        "user_refund_count_30d": int(state.get("user_refund_count_30d", 0)),  # type: ignore[misc]
        "refund_rate_30d": float(state.get("refund_rate_30d", 0)),  # type: ignore[misc]
        "amount_zscore": float(state.get("amount_zscore", 0)),  # type: ignore[misc]
        "device_freq_1h": int(state.get("device_freq_1h", 0)),  # type: ignore[misc]
        "is_duplicate_refund": bool(state.get("is_duplicate_refund", False)),  # type: ignore[misc]
        "cross_tenant_anomaly": bool(state.get("cross_tenant_anomaly", False)),  # type: ignore[misc]
    }


@observe(name="risk_review.run", capture_input=False)
async def run_risk_review(state: AgentState) -> AgentState:
    """节点函数：调三层融合风控，写 risk_decision + needs_review。"""
    from risk import evaluate

    refund_ctx = _extract_refund_context(state)
    tenant_id = state.get("tenant_id")

    try:
        decision = await evaluate(refund_ctx, tenant_id=tenant_id)
    except Exception as exc:
        logger.error("risk evaluate failed: %s", exc)
        # 评估失败 → 保守策略：触发人审
        return AgentState(  # type: ignore[return-value]
            needs_review=True,
            interrupt_reason=f"风控评估失败: {str(exc)[:80]}",
            risk_decision={"decision": "review", "fusion_score": 50.0, "explanation": "评估异常"},
        )

    risk_dict = {
        "decision": decision.decision,
        "fusion_score": decision.fusion_score,
        "explanation": decision.explanation,
        "weights": decision.weights,
        "rules_hits": [{"rule_id": h.rule_id, "description": h.description, "severity": h.severity}
                       for h in decision.rules.hits],
        "features_evidence": decision.features.evidence,
        "llm_reason": decision.llm.reason,
        "llm_unavailable": decision.llm.unavailable,
    }

    needs_review = decision.decision in {"review", "reject"}
    interrupt_reason = decision.explanation if needs_review else None

    logger.info("risk_review: score=%.1f decision=%s needs_review=%s",
                decision.fusion_score, decision.decision, needs_review)

    return AgentState(  # type: ignore[return-value]
        risk_decision=risk_dict,
        needs_review=needs_review,
        interrupt_reason=interrupt_reason,
    )


def route_after_risk_review(state: AgentState) -> str:
    """中断后 resume 时：根据人审决策路由。"""
    decision = (state.get("risk_decision") or {}).get("action", "")
    if decision == "approve":
        return "plan_execute"
    return "__end__"


__all__ = ["run_risk_review", "route_after_risk_review"]
