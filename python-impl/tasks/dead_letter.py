"""tasks/dead_letter.py：Celery 死信队列处理（W5）。

当任务超过 max_retries 后进入死信队列，此模块负责：
1. 记录失败详情到 Redis（key: dlq:{task_id}）
2. 提供管理接口：list_dead / requeue_task / discard_task
3. 告警：死信数量超过阈值时写 warning log（可接 Langfuse 或 Slack webhook）
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_DLQ_PREFIX = "dlq:"
_DLQ_INDEX_KEY = "dlq:index"
_MAX_DLQ_SIZE = 1000
_ALERT_THRESHOLD = 50


# ── Redis 工具 ────────────────────────────────────────────────

def _get_redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis
        return redis.from_url(url, decode_responses=True)
    except Exception as exc:
        logger.warning("DLQ redis connect failed: %s", exc)
        return None


# ── 死信写入（由 Celery failure_handler 调用）─────────────────

def push_dead_letter(
    task_id: str,
    task_name: str,
    args: list,
    kwargs: dict,
    error: str,
    retries: int,
) -> None:
    """将失败任务写入死信队列。"""
    r = _get_redis()
    if r is None:
        logger.error("DLQ push skipped (no Redis): task=%s error=%s", task_id, error)
        return

    entry = {
        "task_id": task_id,
        "task_name": task_name,
        "args": args,
        "kwargs": kwargs,
        "error": str(error)[:500],
        "retries": retries,
        "failed_at": time.time(),
    }
    key = f"{_DLQ_PREFIX}{task_id}"
    try:
        r.set(key, json.dumps(entry, ensure_ascii=False), ex=86400 * 7)  # 7 天 TTL
        r.lpush(_DLQ_INDEX_KEY, task_id)
        r.ltrim(_DLQ_INDEX_KEY, 0, _MAX_DLQ_SIZE - 1)  # 最多保留 1000 条

        dlq_size = r.llen(_DLQ_INDEX_KEY)
        if dlq_size >= _ALERT_THRESHOLD:
            logger.warning("DLQ size %d >= threshold %d — consider manual inspection", dlq_size, _ALERT_THRESHOLD)
        logger.info("DLQ push: task=%s name=%s retries=%d", task_id, task_name, retries)
    except Exception as exc:
        logger.error("DLQ push failed: %s", exc)


# ── 死信查询 ──────────────────────────────────────────────────

def list_dead(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    """列出死信队列条目（最新优先）。"""
    r = _get_redis()
    if r is None:
        return []
    try:
        task_ids = r.lrange(_DLQ_INDEX_KEY, offset, offset + limit - 1)
        entries = []
        for tid in task_ids:
            raw = r.get(f"{_DLQ_PREFIX}{tid}")
            if raw:
                entries.append(json.loads(raw))
        return entries
    except Exception as exc:
        logger.error("DLQ list failed: %s", exc)
        return []


def get_dead(task_id: str) -> dict[str, Any] | None:
    """获取单条死信详情。"""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(f"{_DLQ_PREFIX}{task_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


def discard_dead(task_id: str) -> bool:
    """从死信队列删除（不重试）。"""
    r = _get_redis()
    if r is None:
        return False
    try:
        r.delete(f"{_DLQ_PREFIX}{task_id}")
        r.lrem(_DLQ_INDEX_KEY, 0, task_id)
        logger.info("DLQ discard: task=%s", task_id)
        return True
    except Exception as exc:
        logger.error("DLQ discard failed: %s", exc)
        return False


def requeue_dead(task_id: str) -> bool:
    """将死信条目重新投入 Celery 队列。"""
    entry = get_dead(task_id)
    if entry is None:
        logger.warning("DLQ requeue: task %s not found", task_id)
        return False

    task_name = entry.get("task_name", "")
    args = entry.get("args") or []
    kwargs = entry.get("kwargs") or {}

    try:
        from tasks.celery_app import app as celery_app
        celery_app.send_task(task_name, args=args, kwargs=kwargs)
        discard_dead(task_id)
        logger.info("DLQ requeue success: task=%s name=%s", task_id, task_name)
        return True
    except Exception as exc:
        logger.error("DLQ requeue failed: task=%s error=%s", task_id, exc)
        return False


def dlq_size() -> int:
    """返回当前死信队列长度。"""
    r = _get_redis()
    if r is None:
        return 0
    try:
        return r.llen(_DLQ_INDEX_KEY)
    except Exception:
        return 0


# ── Celery 信号接入 ───────────────────────────────────────────

def register_failure_handler() -> None:
    """注册 Celery task_failure 信号，自动记录死信。

    在 celery_app.py 导入后调用一次：
        from tasks.dead_letter import register_failure_handler
        register_failure_handler()
    """
    try:
        from celery.signals import task_failure

        @task_failure.connect
        def _on_failure(task_id, exception, traceback, einfo, args, kwargs, **extra):
            sender = extra.get("sender")
            task_name = getattr(sender, "name", "unknown") if sender else "unknown"
            retries = getattr(extra.get("request"), "retries", 0) if extra.get("request") else 0
            push_dead_letter(
                task_id=task_id,
                task_name=task_name,
                args=list(args or []),
                kwargs=dict(kwargs or {}),
                error=str(exception),
                retries=retries,
            )

        logger.info("DLQ failure handler registered")
    except ImportError:
        logger.warning("celery not installed, DLQ failure handler skipped")


__all__ = [
    "push_dead_letter",
    "list_dead",
    "get_dead",
    "discard_dead",
    "requeue_dead",
    "dlq_size",
    "register_failure_handler",
]
