# RetailGuard 压测报告

> W7 性能验收文档。压测环境：本地 Docker（4 vCPU / 8GB RAM）。
> 工具：Locust 2.x，50 并发用户，2 分钟稳态。

---

## 测试环境

| 项目 | 值 |
|---|---|
| OS | Windows 11 / Docker Desktop |
| CPU | 4 vCPU |
| RAM | 8 GB |
| Python | 3.13 |
| FastAPI | 0.115+ |
| Workers | uvicorn --workers 4 |
| PostgreSQL | 16 (Docker) |
| Redis | 7 (Docker) |
| Qdrant | 1.11 (Docker) |
| Mock 数据 | 5 租户 / 1000 用户 / 10000 订单 / 5000 工单 |

---

## 场景 1：纯 Chat（简单查询）

- 请求类型：`POST /api/v1/chat`
- 查询：问候 + FAQ 短文本
- 预期路径：intent_router（关键词命中）→ greeting / knowledge

| 指标 | 值 |
|---|---|
| QPS | 待测 |
| P50 | 待测 |
| P95 | 待测 |
| P99 | 待测 |
| 错误率 | 待测 |
| 平均 Token | 待测 |

---

## 场景 2：Chat + RAG（知识检索）

- 请求类型：`POST /api/v1/chat`
- 查询：商品售后政策、退货流程
- 预期路径：intent_router（LLM）→ knowledge（混合检索 + Rerank）

| 指标 | 值 |
|---|---|
| QPS | ~0.14（进程内单线程，见下） |
| P50 | 7554 ms |
| P95 | 8318 ms |
| P99 | — |
| 错误率 | 0% |
| 平均 Token | echo/test 模式 |

> **2026-05-30 进程内采样**（`python -m scripts.bench.quick_perf`，APP_ENV=test，BM25 主检索 + echo LLM）：21 次 knowledge 路径，P50≈7.6s。HTTP 压测需 `docker compose up` 后执行下方 Locust 命令复测；目标 P95&lt;3s 以多 worker + 真实向量化 + 语义缓存为准。

---

## 场景 3：复杂业务（Planner + Critic + Risk）

- 请求类型：`POST /api/v1/chat`
- 查询：退款、订单查询、地址变更
- 预期路径：intent_router → planner → critic → plan_execute → risk_review

| 指标 | 值 |
|---|---|
| QPS | 待测 |
| P50 | 待测 |
| P95 | 待测 |
| P99 | 待测 |
| 错误率 | 待测 |
| 平均 Token | 待测 |

---

## 验收标准

| 标准 | 目标 | 实际 | 状态 |
|---|---|---|---|
| 50 并发 QPS | ≥ 50 | Locust 待 Docker 实测 | ⬜ |
| P95 延迟 | < 3s | 进程内 RAG ~8.3s（test） | ⬜ |
| 缓存命中率 | ≥ 30% | 待 Langfuse 统计 | ⬜ |
| 错误率 | < 1% | 进程内 0% | ✅ |

---

## 压测命令

```bash
# 启动服务
docker-compose up -d
cd python-impl && uvicorn api.main:app --workers 4 --port 8000

# 压测（headless 模式）
locust -f scripts/bench/locustfile.py --host http://localhost:18000 \
  --users 50 --spawn-rate 5 --run-time 2m --headless \
  --csv=docs/eval_reports/perf

# 仅压简单场景
locust -f scripts/bench/locustfile.py --host http://localhost:18000 \
  --users 50 --spawn-rate 5 --run-time 1m --headless --tags simple

# 仅压 RAG 场景
locust -f scripts/bench/locustfile.py --host http://localhost:18000 \
  --users 50 --spawn-rate 5 --run-time 1m --headless --tags rag

# 仅压复杂场景
locust -f scripts/bench/locustfile.py --host http://localhost:18000 \
  --users 50 --spawn-rate 5 --run-time 1m --headless --tags complex
```

---

## 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-27 | W7 初版：压测框架 + 场景定义 + 验收标准 |
| 2026-05-30 | 补充 quick_perf 进程内 RAG 延迟采样 |
