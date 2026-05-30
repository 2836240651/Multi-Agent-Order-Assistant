"""risk/fusion.py：三层加权融合 → 决策（pass/review/reject）+ 可解释决策链。

权重从 config/risk_weights.yaml 读取，支持 Redis 热加载。
LLM 不可用时自动重归一化 rules+features 权重。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from risk.rules import RulesResult
from risk.features import FeaturesResult
from risk.llm_scorer import LLMResult

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parents[1] / "config" / "risk_weights.yaml"

_DEFAULT_CONFIG = {
    "default": {
        "rules": 0.40,
        "features": 0.30,
        "llm": 0.30,
        "thresholds": {"pass": 30, "review": 60, "reject": 90},
    }
}


# ── 权重加载 ──────────────────────────────────────────────────

def _load_weights() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        try:
            with _CONFIG_PATH.open(encoding="utf-8") as f:
                return yaml.safe_load(f) or _DEFAULT_CONFIG
        except Exception as exc:
            logger.warning("risk_weights.yaml load failed: %s", exc)
    return _DEFAULT_CONFIG


def _get_config(tenant_id: int | None = None) -> dict[str, Any]:
    """优先从 Redis 读取热更新权重，否则 fallback yaml。"""
    try:
        import json
        import os
        redis_url = os.getenv("REDIS_URL", "")
        if not redis_url:
            raise RuntimeError("no redis")
        import redis as redis_lib
        r = redis_lib.from_url(redis_url, decode_responses=True)
        key = f"risk_weights:{tenant_id or 'default'}"
        raw = r.get(key)
        if raw:
            return {"default": json.loads(raw)}
    except Exception:
        pass
    return _load_weights()


# ── 融合模型 ──────────────────────────────────────────────────

@dataclass
class RiskDecision:
    fusion_score: float
    decision: Literal["pass", "review", "reject"]
    rules: RulesResult
    features: FeaturesResult
    llm: LLMResult
    weights: dict[str, float]
    explanation: str
    tenant_id: int | None = None


def _decision_from_score(score: float, thresholds: dict) -> Literal["pass", "review", "reject"]:
    if score >= thresholds.get("reject", 90):
        return "reject"
    if score >= thresholds.get("review", 60):
        return "review"
    return "pass"


def fuse(
    rules_result: RulesResult,
    features_result: FeaturesResult,
    llm_result: LLMResult,
    tenant_id: int | None = None,
) -> RiskDecision:
    """三层加权融合并生成可解释决策。"""
    cfg = _get_config(tenant_id).get("default", _DEFAULT_CONFIG["default"])
    w_rules = float(cfg.get("rules", 0.4))
    w_features = float(cfg.get("features", 0.3))
    w_llm = float(cfg.get("llm", 0.3))
    thresholds = cfg.get("thresholds", {"pass": 30, "review": 60, "reject": 90})

    # LLM 不可用时重归一化
    if llm_result.unavailable:
        total = w_rules + w_features
        if total > 0:
            w_rules = w_rules / total
            w_features = w_features / total
        w_llm = 0.0

    fusion_score = (
        rules_result.score * w_rules
        + features_result.score * w_features
        + llm_result.score * w_llm
    )
    fusion_score = round(min(100.0, fusion_score), 2)

    # 关键规则直接升级决策（critical hit → 至少 review）
    decision = _decision_from_score(fusion_score, thresholds)
    if not rules_result.passed and decision == "pass":
        decision = "review"

    weights = {"rules": round(w_rules, 3), "features": round(w_features, 3), "llm": round(w_llm, 3)}

    # 可解释说明
    parts = []
    if rules_result.hits:
        hit_descs = "；".join(h.description for h in rules_result.hits[:3])
        parts.append(f"规则命中：{hit_descs}")
    anom_names = [a.name for a in features_result.anomalies if a.is_anomalous]
    if anom_names:
        parts.append(f"特征异常：{', '.join(anom_names[:3])}")
    if not llm_result.unavailable:
        parts.append(f"LLM 评估：{llm_result.reason}")
    else:
        parts.append("LLM 不可用（已重归一化权重）")
    explanation = "；".join(parts) if parts else "无异常，正常通过"

    return RiskDecision(
        fusion_score=fusion_score,
        decision=decision,
        rules=rules_result,
        features=features_result,
        llm=llm_result,
        weights=weights,
        explanation=explanation,
        tenant_id=tenant_id,
    )


__all__ = ["RiskDecision", "fuse"]
