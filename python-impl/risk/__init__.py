"""risk/__init__.py：暴露 evaluate() 单一入口。

调用方：
    from risk import evaluate
    decision = await evaluate(refund_dict, tenant_id=1)
"""
from __future__ import annotations

import logging
from typing import Any

from risk.features import evaluate_features
from risk.fusion import RiskDecision, fuse
from risk.llm_scorer import evaluate_llm
from risk.normalize import normalize_risk_refund
from risk.rules import evaluate_rules

logger = logging.getLogger(__name__)


async def evaluate(
    refund: dict[str, Any],
    tenant_id: int | None = None,
    *,
    user: dict[str, Any] | None = None,
) -> RiskDecision:
    """三层风控评估入口。

    参数 refund 字典包含退款申请所有字段（见 risk/AGENTS.md §3）。
    可选 user 子字典用于评测/API 异构字段归一。
    """
    refund = normalize_risk_refund(refund, user)
    rules_result = evaluate_rules(refund)
    features_result = evaluate_features(refund)
    llm_result = await evaluate_llm(refund)
    decision = fuse(rules_result, features_result, llm_result, tenant_id=tenant_id)
    logger.info(
        "risk evaluate: score=%.1f decision=%s llm_unavailable=%s",
        decision.fusion_score, decision.decision, llm_result.unavailable,
    )
    return decision


__all__ = ["evaluate", "RiskDecision"]
