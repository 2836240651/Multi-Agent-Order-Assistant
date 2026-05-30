"""tasks/batch_jobs.py：批量异步任务定义。

任务：
- batch_review：批量风控审核（客服触发 50 条工单）
- ingest_kb_task：后台灌库（大文件异步处理）
- run_eval_task：后台运行评测集
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from tasks.celery_app import app
from tasks.progress import update_progress
from risk import evaluate

logger = logging.getLogger(__name__)


def _fetch_refund_context(ticket_id: str, tenant_id: int) -> dict[str, Any]:
    """从工单 ID 拼装风控评估上下文。

    W5 阶段用 mock 数据；接入 MCP/DB 后替换为真实查询。
    """
    return {
        "ticket_id": ticket_id,
        "tenant_id": tenant_id,
        "amount": 0.0,
        "reason": "",
        "description": "",
        "product_name": "",
        "days_since_delivery": 0,
        "days_since_order": 0,
        "user_refund_count_30d": 0,
        "refund_rate_30d": 0.0,
        "amount_zscore": 0.0,
        "device_freq_1h": 0,
        "is_duplicate_refund": False,
        "cross_tenant_anomaly": False,
    }


@app.task(bind=True, name="tasks.batch_jobs.batch_review", max_retries=3)
def batch_review(self, ticket_ids: list[str], tenant_id: int = 1) -> dict[str, Any]:
    """批量风控审核任务。

    对 ticket_ids 中每条工单运行三层风控，更新 Redis 进度。
    """
    import asyncio

    task_id = self.request.id
    total = len(ticket_ids)
    update_progress(task_id, status="running", done=0, total=total, message="开始批量风控审核")

    results: list[dict] = []
    for i, tid in enumerate(ticket_ids):
        try:
            refund_ctx = _fetch_refund_context(tid, tenant_id)
            decision = asyncio.run(evaluate(refund_ctx, tenant_id=tenant_id))
            results.append({
                "ticket_id": tid,
                "decision": decision.decision,
                "fusion_score": decision.fusion_score,
                "explanation": decision.explanation,
            })
        except Exception as exc:
            logger.warning("batch_review ticket %s failed: %s", tid, exc)
            results.append({"ticket_id": tid, "decision": "error", "error": str(exc)})

        update_progress(task_id, status="running", done=i + 1, total=total,
                        message=f"处理 {i + 1}/{total}")

    passed = sum(1 for r in results if r.get("decision") == "pass")
    reviewed = sum(1 for r in results if r.get("decision") == "review")
    rejected = sum(1 for r in results if r.get("decision") == "reject")
    update_progress(
        task_id, status="done", done=total, total=total,
        message=f"完成：通过 {passed} / 人审 {reviewed} / 拒绝 {rejected}",
    )
    return {"task_id": task_id, "total": total, "results": results}


@app.task(bind=True, name="tasks.batch_jobs.ingest_kb_task", max_retries=2)
def ingest_kb_task(self, kb_dir: str, tenant_id: int = 1) -> dict[str, Any]:
    """后台知识库灌库任务。"""
    import asyncio
    from pathlib import Path

    task_id = self.request.id
    kb_path = Path(kb_dir)
    files = list(kb_path.glob("*.md")) if kb_path.exists() else []
    total = len(files)
    update_progress(task_id, status="running", done=0, total=total, message=f"灌库：{total} 个文件")

    for i, f in enumerate(files):
        try:
            # W5 mock：实际调 asyncio.run(ingest_kb.ingest_file(f, tenant_id))
            time.sleep(0.02)
        except Exception as exc:
            logger.warning("ingest file %s failed: %s", f, exc)
        update_progress(task_id, status="running", done=i + 1, total=total)

    update_progress(task_id, status="done", done=total, total=total, message="灌库完成")
    return {"task_id": task_id, "files_ingested": total}


@app.task(bind=True, name="tasks.batch_jobs.run_eval_task", max_retries=1)
def run_eval_task(self, dataset: str = "all", sample: int = 10) -> dict[str, Any]:
    """后台运行评测。"""
    import asyncio

    task_id = self.request.id
    update_progress(task_id, status="running", done=0, total=1, message=f"启动评测：{dataset}")

    try:
        from eval.runner import EvalRunner
        runner = EvalRunner(
            categories=[dataset] if dataset != "all" else None,
            sample=sample,
        )
        results = asyncio.run(runner.run())
        passed = sum(1 for r in results if r.pass_)
        update_progress(task_id, status="done", done=1, total=1,
                        message=f"评测完成：{passed}/{len(results)} passed")
        return {"task_id": task_id, "total": len(results), "passed": passed}
    except Exception as exc:
        update_progress(task_id, status="failed", done=0, total=1, message=str(exc))
        raise


def run_batch_review_sync(
    ticket_ids: list[str],
    tenant_id: int = 1,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Celery 不可用時的同步批量風控（進度寫 Redis 或內存）。"""
    import asyncio

    tid = task_id or f"sync-{uuid.uuid4().hex[:12]}"
    total = len(ticket_ids)
    update_progress(tid, status="running", done=0, total=total, message="同步批量風控")

    results: list[dict] = []
    for i, ticket_id in enumerate(ticket_ids):
        try:
            refund_ctx = _fetch_refund_context(ticket_id, tenant_id)
            decision = asyncio.run(evaluate(refund_ctx, tenant_id=tenant_id))
            results.append({
                "ticket_id": ticket_id,
                "decision": decision.decision,
                "fusion_score": decision.fusion_score,
            })
        except Exception as exc:
            results.append({"ticket_id": ticket_id, "decision": "error", "error": str(exc)})
        update_progress(
            tid, status="running", done=i + 1, total=total,
            message=f"處理 {i + 1}/{total}",
        )

    update_progress(tid, status="done", done=total, total=total, message="同步批量完成")
    return {"task_id": tid, "total": total, "results": results, "mode": "sync"}


__all__ = ["batch_review", "ingest_kb_task", "run_eval_task", "run_batch_review_sync"]
