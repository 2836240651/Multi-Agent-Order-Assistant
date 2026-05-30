"""risk/rules.py：硬规则层，10 条规则，每条独立可单测。

规则输出：score 0-100 + 命中列表。任何命中 reject 规则直接触发最高分。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── 数据模型 ──────────────────────────────────────────────────

@dataclass
class RuleHit:
    rule_id: str
    description: str
    score_contribution: float  # 该规则贡献的分数 0-100
    severity: str  # "low" | "medium" | "high" | "critical"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class RulesResult:
    score: float          # 融合后规则层总分 0-100
    hits: list[RuleHit]
    passed: bool          # True = 规则层无高危命中


# ── 规则定义 ──────────────────────────────────────────────────

# 金额阈值（元）
_AMOUNT_THRESHOLDS = {
    "low": 100.0,
    "medium": 500.0,
    "high": 2000.0,
    "critical": 5000.0,
}

# 退款频次（近 30 天允许次数）
_REFUND_FREQ_LIMIT = 5

# 地址跳变（km，同一用户近 7 天内）
_ADDRESS_JUMP_KM = 500.0

# 黑名单关键词（描述字段）
_BLACKLIST_KEYWORDS = [
    "批量", "代退", "代刷", "洗单", "套现", "测试订单", "测试退款",
]

# 超期退款（天）
_OVERDUE_DAYS = 7


def _rule_amount_critical(refund: dict[str, Any]) -> RuleHit | None:
    amt = float(refund.get("amount", 0))
    if amt >= _AMOUNT_THRESHOLDS["critical"]:
        return RuleHit("R-001", "退款金额超过 5000 元", 80.0, "critical", {"amount": amt})
    return None


def _rule_amount_medium(refund: dict[str, Any]) -> RuleHit | None:
    amt = float(refund.get("amount", 0))
    if _AMOUNT_THRESHOLDS["medium"] <= amt < _AMOUNT_THRESHOLDS["high"]:
        return RuleHit("R-002b", "退款金额 500-2000 元", 95.0, "medium", {"amount": amt})
    return None


def _rule_amount_high(refund: dict[str, Any]) -> RuleHit | None:
    amt = float(refund.get("amount", 0))
    if _AMOUNT_THRESHOLDS["high"] <= amt < _AMOUNT_THRESHOLDS["critical"]:
        return RuleHit("R-002", "退款金额 2000-5000 元", 55.0, "high", {"amount": amt})
    return None


def _rule_high_refund_rate(refund: dict[str, Any]) -> RuleHit | None:
    rate = float(refund.get("refund_rate_30d", 0))
    if rate >= 0.7:
        return RuleHit("R-011", f"近 30 天退款率 {rate:.0%}", 60.0, "high", {"refund_rate_30d": rate})
    if rate >= 0.45:
        return RuleHit("R-012", f"近 30 天退款率偏高 {rate:.0%}", 40.0, "medium", {"refund_rate_30d": rate})
    return None


def _rule_overdue(refund: dict[str, Any]) -> RuleHit | None:
    days = int(refund.get("days_since_delivery", 0))
    if days > _OVERDUE_DAYS:
        return RuleHit("R-003", f"超期退款（{days} 天，限 {_OVERDUE_DAYS} 天）", 70.0, "high", {"days": days})
    return None


def _rule_high_freq(refund: dict[str, Any]) -> RuleHit | None:
    freq = int(refund.get("user_refund_count_30d", 0))
    if freq >= _REFUND_FREQ_LIMIT:
        return RuleHit("R-004", f"近 30 天退款 {freq} 次（限 {_REFUND_FREQ_LIMIT}）", 60.0, "high", {"count": freq})
    return None


def _rule_address_jump(refund: dict[str, Any]) -> RuleHit | None:
    km = float(refund.get("address_jump_km", 0))
    if km >= _ADDRESS_JUMP_KM:
        return RuleHit("R-005", f"收货地址跳变 {km:.0f} km", 55.0, "medium", {"km": km})
    return None


def _rule_blacklist_keyword(refund: dict[str, Any]) -> RuleHit | None:
    desc = str(refund.get("description", "")).lower()
    for kw in _BLACKLIST_KEYWORDS:
        if kw in desc:
            return RuleHit("R-006", f"描述含黑名单关键词「{kw}」", 90.0, "critical", {"keyword": kw})
    return None


def _rule_new_user(refund: dict[str, Any]) -> RuleHit | None:
    days = int(refund.get("user_age_days", 999))
    amt = float(refund.get("amount", 0))
    if days < 7 and amt > 300:
        return RuleHit("R-007", f"新用户（{days} 天）高额退款", 65.0, "high", {"user_age_days": days, "amount": amt})
    return None


def _rule_zero_amount(refund: dict[str, Any]) -> RuleHit | None:
    amt = float(refund.get("amount", 0))
    if amt <= 0:
        return RuleHit("R-008", "退款金额为零或负数", 85.0, "critical", {"amount": amt})
    return None


def _rule_duplicate_order(refund: dict[str, Any]) -> RuleHit | None:
    if refund.get("is_duplicate_refund", False):
        return RuleHit("R-009", "同订单重复退款申请", 95.0, "critical", {})
    return None


def _rule_cross_tenant(refund: dict[str, Any]) -> RuleHit | None:
    if refund.get("cross_tenant_anomaly", False):
        return RuleHit("R-010", "跨租户异常请求", 100.0, "critical", {})
    return None


_RULE_CHECKS = [
    _rule_amount_critical, _rule_amount_high, _rule_amount_medium, _rule_high_refund_rate,
    _rule_overdue, _rule_high_freq,
    _rule_address_jump, _rule_blacklist_keyword, _rule_new_user,
    _rule_zero_amount, _rule_duplicate_order, _rule_cross_tenant,
]


# ── 主入口 ────────────────────────────────────────────────────

def evaluate_rules(refund: dict[str, Any]) -> RulesResult:
    """运行所有规则，返回命中列表和聚合分。"""
    hits: list[RuleHit] = []
    for check in _RULE_CHECKS:
        hit = check(refund)
        if hit is not None:
            hits.append(hit)

    if not hits:
        return RulesResult(score=0.0, hits=[], passed=True)

    max_score = max(h.score_contribution for h in hits)
    count_penalty = min(len(hits) * 8, 24)
    score = min(100.0, max_score * 0.75 + count_penalty * 0.25)

    critical_hit = any(h.severity == "critical" for h in hits)
    return RulesResult(score=score, hits=hits, passed=not critical_hit)


__all__ = ["RuleHit", "RulesResult", "evaluate_rules"]
