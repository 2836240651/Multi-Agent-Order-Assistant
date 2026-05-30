"""risk/features.py：在线特征层 — 用户行为统计 + 金额 z-score + 设备频次。

W4 实现：从 refund dict 提取已计算好的特征，进行异常判断。
生产环境中特征由离线管道预计算后写入 Redis；此处以 dict 参数模拟。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FeatureAnomaly:
    name: str
    value: float
    threshold: float
    is_anomalous: bool
    contribution: float  # 0-100


@dataclass
class FeaturesResult:
    score: float
    evidence: dict[str, Any]
    anomalies: list[FeatureAnomaly]


# ── 特征阈值配置 ──────────────────────────────────────────────

_THRESHOLDS = {
    "refund_rate_30d": 0.3,       # 近30天退款率 > 30% 异常
    "amount_zscore": 2.5,         # 金额 z-score 异常阈值
    "device_freq_1h": 5,          # 同设备 1h 内请求次数
    "ip_change_count_7d": 3,      # 近7天 IP 变更次数
    "complaint_count_90d": 3,     # 近90天投诉次数
}


def _check_feature(name: str, value: float, threshold: float, weight: float) -> FeatureAnomaly:
    is_anom = value > threshold
    contribution = min(100.0, (value / max(threshold, 1e-9)) * weight * 50) if is_anom else 0.0
    return FeatureAnomaly(name=name, value=value, threshold=threshold,
                          is_anomalous=is_anom, contribution=contribution)


def evaluate_features(refund: dict[str, Any]) -> FeaturesResult:
    """从 refund 字典中读取预计算特征，输出异常评分。"""
    checks: list[tuple[str, str, float]] = [
        ("refund_rate_30d",    "refund_rate_30d",    0.4),
        ("amount_zscore",      "amount_zscore",       0.3),
        ("device_freq_1h",     "device_freq_1h",      0.2),
        ("ip_change_count_7d", "ip_change_count_7d",  0.05),
        ("complaint_count_90d","complaint_count_90d", 0.05),
    ]

    anomalies: list[FeatureAnomaly] = []
    for feat_name, dict_key, weight in checks:
        val = float(refund.get(dict_key, 0))
        threshold = _THRESHOLDS[feat_name]
        anomalies.append(_check_feature(feat_name, val, threshold, weight))

    total_contribution = sum(a.contribution for a in anomalies)
    score = min(100.0, total_contribution)

    evidence = {
        a.name: {
            "value": a.value,
            "threshold": a.threshold,
            "anomalous": a.is_anomalous,
        }
        for a in anomalies
    }

    return FeaturesResult(score=score, evidence=evidence, anomalies=anomalies)


__all__ = ["FeatureAnomaly", "FeaturesResult", "evaluate_features"]
