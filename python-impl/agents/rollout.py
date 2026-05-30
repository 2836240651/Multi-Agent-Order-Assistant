"""agents/rollout.py：灰度发布管理器。

存储 version → weight 的 Redis hash；decide() 按确定性 hash 选版本（同用户同天稳定）。
支持 /api/v1/admin/rollout GET/PUT 热更新 + 审计日志。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import date
from typing import Any, Literal

logger = logging.getLogger(__name__)

_REDIS_KEY = "rollout:weights"
_AUDIT_KEY = "rollout:audit"
_MAX_AUDIT = 200
_DEFAULT_WEIGHTS: dict[str, float] = {"v1": 0.0, "v2": 0.0, "v3": 1.0}
Version = Literal["v1", "v2", "v3"]


def _get_redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis
        return redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def get_weights() -> dict[str, float]:
    """读取当前灰度权重（Redis → fallback 默认）。"""
    r = _get_redis()
    if r:
        try:
            raw = r.get(_REDIS_KEY)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning("rollout get_weights failed: %s", exc)
    return dict(_DEFAULT_WEIGHTS)


def set_weights(weights: dict[str, float], *, operator: str = "admin") -> None:
    """更新灰度权重（写 Redis + 写 audit_log）。"""
    # 归一化
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to > 0")
    normalized = {k: round(v / total, 4) for k, v in weights.items()}

    old_weights = get_weights()
    r = _get_redis()
    if r:
        try:
            r.set(_REDIS_KEY, json.dumps(normalized))
            # 审计日志
            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "operator": operator,
                "old": old_weights,
                "new": normalized,
            }
            r.lpush(_AUDIT_KEY, json.dumps(entry, ensure_ascii=False))
            r.ltrim(_AUDIT_KEY, 0, _MAX_AUDIT - 1)
        except Exception as exc:
            logger.warning("rollout set_weights Redis failed: %s", exc)

    logger.info("rollout weights updated: %s (by %s)", normalized, operator)


def get_audit_log(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """读取灰度变更审计日志（最新优先）。"""
    r = _get_redis()
    if r is None:
        return []
    try:
        raw_list = r.lrange(_AUDIT_KEY, offset, offset + limit - 1)
        return [json.loads(item) for item in raw_list]
    except Exception as exc:
        logger.warning("rollout get_audit_log failed: %s", exc)
        return []


def decide(
    version_hint: str | None = None,
    *,
    user_id: int | str | None = None,
    tenant_id: int | str | None = None,
) -> Version:
    """确定性灰度选版本：同一 user+tenant+日期 始终命中同版本。

    version_hint 可强制指定（用于测试/调试）。
    """
    if version_hint in {"v1", "v2", "v3"}:
        return version_hint  # type: ignore[return-value]

    weights = get_weights()
    versions = sorted(weights.keys())
    w_list = [weights.get(v, 0.0) for v in versions]
    total = sum(w_list)
    if total <= 0:
        return "v3"

    seed = f"{user_id or 'anon'}:{tenant_id or 0}:{date.today().isoformat()}"
    h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    bucket = (h % 10000) / 10000.0 * total

    cumsum = 0.0
    for v, w in zip(versions, w_list):
        cumsum += w
        if bucket < cumsum:
            return v  # type: ignore[return-value]
    return "v3"


__all__ = ["get_weights", "set_weights", "decide", "get_audit_log"]
