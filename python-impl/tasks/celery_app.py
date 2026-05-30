"""tasks/celery_app.py：Celery 应用配置。

队列：
- review：人审批量任务
- ingest：知识库灌库
- eval：评测运行

用法：
    celery -A tasks.celery_app worker --loglevel=info -Q review,ingest,eval
"""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:16379/0")

app = Celery(
    "retailguard",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.batch_jobs"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_routes={
        "tasks.batch_jobs.batch_review": {"queue": "review"},
        "tasks.batch_jobs.ingest_kb_task": {"queue": "ingest"},
        "tasks.batch_jobs.run_eval_task": {"queue": "eval"},
    },
    task_track_started=True,
    result_expires=3600,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# 注册死信处理器（仅 worker 进程中生效）
try:
    from tasks.dead_letter import register_failure_handler
    register_failure_handler()
except Exception:
    pass

__all__ = ["app"]
