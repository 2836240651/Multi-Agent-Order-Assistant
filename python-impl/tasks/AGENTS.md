# tasks/ · Celery 异步任务 AGENTS.md

> 长耗时 / 批量 / 后台任务的归宿。W5 落地。

---

## 1. 模块组成

| 文件 | 职责 |
|---|---|
| `celery_app.py` | Celery 实例 + 路由配置（按队列） |
| `batch_jobs.py` | 业务任务定义：`batch_review`（接 risk.evaluate）/ `ingest_kb_task` / `run_eval_task` |
| `progress.py` | 进度追踪（Redis hash），供 WS 和 HTTP 轮询读取 |
| `dead_letter.py` | 死信队列：push/list/get/discard/requeue + Celery 信号自动接入 |

---

## 2. 队列规划

| 队列 | 任务 | worker 数 |
|---|---|---|
| `review` | 批量审核 | 2 |
| `ingest` | KB 重建索引 | 1 |
| `eval` | 长时评测 | 1 |

---

## 3. 不变量

- 每个任务 `bind=True, max_retries=3`，失败进死信
- 进度推送通过 Redis pub/sub；前端 WS 断线 fallback 轮询 `/tasks/{id}`
- 任务函数不允许直调 LLM SDK（同样走 `llm.router`）
- 任务结果与日志写 PG `tasks` 表；不存大对象（>1MB 写文件，存路径）

---

## 4. 数据契约

```python
class Task(BaseModel):
    id: str  # uuid
    tenant_id: int
    type: Literal["batch_refund_review", "reindex_kb", "eval_run"]
    status: Literal["queued", "running", "succeeded", "failed", "stopped"]
    progress: int  # 0-100
    payload: dict
    result: dict | None
    created_at: datetime
    updated_at: datetime
```

---

## 5. 测试

- `tests/integration/tasks/` — 用 `celery.contrib.testing.worker` 启临时 worker
- 进度推送的单测通过 mock `WSPusher`

---

## 6. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-27 | W5 落地：celery_app.py 三队列路由（review/ingest/eval）；batch_review 接 risk.evaluate() 真实风控；progress.py Redis hash 进度追踪；dead_letter.py 完整死信处理 + Celery 信号自动接入；WebSocket /ws/tasks/{id} 实时推送；rollout 审计日志 |
| 2026-05-25 | 占位，W5 落地 |
