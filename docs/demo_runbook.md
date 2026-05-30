# RetailGuard 演示走查清单（12 条）

> 对应 [PRD.md §8](PRD.md) 与 `python-impl/tests/agent_replay/test_demos.py` 自动化回放。
> 自动化验证：`cd python-impl && APP_ENV=test RAG_USE_LOCAL_FALLBACK=true pytest tests/agent_replay/test_demos.py -v`

## 前置

```bash
docker compose up -d
cd python-impl && python -m scripts.bootstrap
cd python-impl && python -m scripts.ingest_kb --kb ../docs/knowledge_base
```

演示账号见 `scripts/bootstrap.py`（顾客 `demo_customer_1` / 123456 / tenant-a）。

**能力矩阵一键探測**：管理员登入 → `/admin/capabilities`（或仪表板「能力矩阵」），對照「代碼存在 / 可演示」兩列。API：`GET /api/v1/admin/capabilities`。

`bootstrap` 結束後會自動 `ensure_kb_indexed`；API 啟動時亦會灌庫（可設 `SKIP_KB_BOOTSTRAP=1` 關閉）。

| # | 主题 | 关键操作 | 自动化用例 |
|---|------|----------|------------|
| 1 | 知识问答 | ChatView 提问 + 引用抽屉 | `test_demo_01_knowledge_qa` |
| 2 | 查单 + 跨租户 | ORD 本租户/他租户 | `test_demo_02_order_query` |
| 3 | 复杂多步 | Planner 拆步 | `test_demo_03_complex_refund` |
| 4 | 风控人审 | 高额退款 → Approve resume | `test_demo_04_risk_interrupt` |
| 5 | 模型路由 | 问候 vs 复杂请求 trace | `test_demo_05_model_routing` |
| 6 | 语义缓存 | 同义问法二次加速 | `test_demo_06_semantic_cache` |
| 7 | 异步任务 | 批量审核进度 | `test_demo_07_async_task` |
| 8 | 灰度 | RolloutView 调权重 | `test_demo_08_rollout` |
| 9 | 多租户 | 管理员仅见本租户 | `test_demo_09_tenant_isolation` |
| 10 | 观测 | Langfuse trace 树 | `test_demo_10_observability` |
| 11 | 评测 | `make eval-smoke` | `test_demo_11_eval_report` |
| 12 | MCP | `query_order` 工具 | `test_demo_12_mcp_tools` |

## 录屏建议

每条 < 30s，按上表顺序录制；第 1 条务必展示引用抽屉与 Langfuse trace。

## 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-05-30 | 初版：对齐 PRD §8 + agent_replay 用例名 |
| 2026-05-30 | 新增 `/admin/capabilities`、bootstrap/API 自動 KB、Celery 同步 fallback |
