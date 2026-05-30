"""risk/normalize.py：将评测/API 异构字段归一为 rules/features/llm 层契约。"""
from __future__ import annotations

import math
from typing import Any


def normalize_risk_refund(refund_data: dict[str, Any], user_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """合并 refund + user 字典，补齐风控模块所需字段名。"""
    user_data = user_data or {}
    amount = float(refund_data.get("amount", 0) or 0)
    reason = str(refund_data.get("reason", "") or "")
    description = str(refund_data.get("description", "") or reason)
    days_signed = int(refund_data.get("days_since_signed", refund_data.get("days_since_delivery", 7)) or 7)
    refund_rate = float(user_data.get("refund_rate_30d", refund_data.get("refund_rate_30d", 0)) or 0)
    total_orders = int(user_data.get("total_orders", refund_data.get("user_total_orders", 10)) or 10)
    refund_count = int(
        refund_data.get(
            "user_refund_count_30d",
            user_data.get("user_refund_count_30d", max(0, round(refund_rate * total_orders))),
        )
        or 0
    )

    # 金额 z-score：相对 500 元基准的简化估计（评测/无历史数据时）
    amount_zscore = float(refund_data.get("amount_zscore", abs(amount - 500) / 250.0 if amount else 0))
    if amount >= 500:
        amount_zscore = max(amount_zscore, 2.8)

    return {
        "order_no": refund_data.get("order_no", ""),
        "amount": amount,
        "reason": reason,
        "description": description,
        "product_name": refund_data.get("product_name", "商品"),
        "days_since_delivery": days_signed,
        "days_since_order": int(refund_data.get("days_since_order", days_signed + 2)),
        "user_refund_count_30d": refund_count,
        "refund_rate_30d": refund_rate,
        "amount_zscore": amount_zscore,
        "device_freq_1h": int(refund_data.get("device_freq_1h", user_data.get("device_freq_1h", 1))),
        "ip_change_count_7d": int(refund_data.get("ip_change_count_7d", 0)),
        "complaint_count_90d": int(refund_data.get("complaint_count_90d", 0)),
        "user_age_days": int(refund_data.get("user_age_days", user_data.get("user_age_days", 365))),
        "address_jump_km": float(refund_data.get("address_jump_km", 0)),
        "is_duplicate_refund": bool(refund_data.get("is_duplicate_refund", False)),
        "cross_tenant_anomaly": bool(refund_data.get("cross_tenant_anomaly", False)),
    }


__all__ = ["normalize_risk_refund"]
