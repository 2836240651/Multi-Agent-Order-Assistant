"""tasks/progress.py：任务进度追踪（Redis hash）。

进度格式（存 Redis key task:{task_id}:progress）：
    {"task_id": str, "status": "pending|running|done|failed",
     "total": int, "done": int, "pct": float, "message": str}
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:16379/0")
_TTL = 86400  # 1 day
_MEMORY: dict[str, dict[str, Any]] = {}


def _client():
    try:
        import redis
        return redis.from_url(_REDIS_URL, decode_responses=True)
    except Exception:
        return None


def update_progress(task_id: str, *, status: str, done: int, total: int, message: str = "") -> None:
    pct = round(done / max(1, total) * 100, 1)
    data = {
        "task_id": task_id,
        "status": status,
        "total": total,
        "done": done,
        "pct": pct,
        "message": message,
    }
    r = _client()
    if r is None:
        _MEMORY[task_id] = data
        return
    try:
        r.set(f"task:{task_id}:progress", json.dumps(data), ex=_TTL)
    except Exception as exc:
        logger.warning("progress update failed: %s", exc)
        _MEMORY[task_id] = data


def get_progress(task_id: str) -> dict[str, Any] | None:
    r = _client()
    if r is None:
        return _MEMORY.get(task_id)
    try:
        raw = r.get(f"task:{task_id}:progress")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return _MEMORY.get(task_id)


__all__ = ["update_progress", "get_progress"]
