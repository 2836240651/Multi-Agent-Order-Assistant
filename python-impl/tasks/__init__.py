"""tasks 包：Celery 异步任务（W5）。

celery 可选依赖：无 celery 时模块可导入，但 celery 功能不可用。
"""
from __future__ import annotations

try:
    from tasks.celery_app import app
    from tasks.batch_jobs import batch_review, ingest_kb_task, run_eval_task
    __all__ = ["app", "batch_review", "ingest_kb_task", "run_eval_task"]
except ImportError:
    __all__ = []
