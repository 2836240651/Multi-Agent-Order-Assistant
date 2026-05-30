# RetailGuard Copilot

> 企业级 AI 售后客服系统 · 7-Agent 协作 · 三层融合风控 · 三版本灰度 · 全链路可观测

[![CI](https://github.com/yourname/retailguard-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/yourname/retailguard-copilot/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-≥70%25-brightgreen)](https://github.com/yourname/retailguard-copilot/actions/workflows/ci.yml)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.3+-blue)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/docker-compose-ready-blue)](docker-compose.yml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Highlights

- **7-Agent 协作拓扑**：supervisor → intent_router → planner → critic → plan_execute → risk_review → knowledge，LangGraph StateGraph 编排
- **三层融合风控**：规则层（10 条硬规则）+ 特征层（用户行为异常检测）+ LLM 语义评估，加权融合 + 可解释决策链
- **三版本灰度**：V1（关键词基线）→ V2（LLM 意图 + 规则风控）→ V3（全 7-Agent + 三层风控），确定性 hash 分流
- **RAG 知识库**：混合检索（BM25 + 向量）+ Reranker，Top1 命中率 ≥ 80%
- **5 维度评测**：intent / tool_call / rag / risk / e2e 共 200 条用例，Langfuse 全链路 trace
- **MCP 协议**：官方 SDK stdio，4 工具（query_order / list_refunds / get_kb_doc / risk_check），Claude Desktop 直接调用
- **JWT + RBAC**：4 角色（顾客/客服/风控/管理员）× 25 权限点，按钮级权限控制
- **5 租户隔离**：ContextVar 自动注入 tenant_id，跨租户访问拦截 + 审计日志
- **Celery 异步**：批量风控审核 / 知识库灌库 / 评测运行，WebSocket 实时进度推送
- **语义缓存**：Redis VSS，cosine ≥ 0.92 命中，豁免敏感操作，预期成本下降 30%+

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Vue3 + Vite 前端                         │
│  顾客 ChatView │ 客服 AgentDashboard │ 风控 ReviewQueue │ 管理员 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ SSE / REST / WS
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI + JWT + RBAC                          │
│  /api/v1/chat │ /admin/rollout │ /review/{id}/resume │ /ws/...  │
└──────┬───────────┬───────────┬──────────────┬───────────────────┘
       │           │           │              │
┌──────▼──────┐ ┌──▼────┐ ┌───▼───┐ ┌────────▼────────┐
│  LangGraph  │ │ RAG   │ │ Risk  │ │ Celery Workers  │
│  Supervisor │ │ 混合   │ │ 三层   │ │ review/ingest/  │
│  7-Node     │ │ 检索   │ │ 融合   │ │ eval            │
│  StateGraph │ │ Rerank │ │ 风控   │ │                 │
└──────┬──────┘ └───┬───┘ └───┬───┘ └────────┬────────┘
       │            │         │              │
┌──────▼────────────▼─────────▼──────────────▼───────────────────┐
│  PostgreSQL │ Redis │ Qdrant │ Langfuse │ MCP Server (stdio)   │
└─────────────────────────────────────────────────────────────────┘
```

### Agent 拓扑

```
START → intent_router ─┬─ greeting ──────────────────► END
                       ├─ knowledge ─────────────────► END
                       └─ planner → critic ─┬─ plan_execute ─► END
                                            ├─ planner (revise)
                                            └─ risk_review (interrupt) ─► END
```

### 三版本对比

| 维度 | V1（基线） | V2（工具+规则） | V3（全功能） |
|---|---|---|---|
| 意图识别 | 关键词 | LLM | LLM + 复杂度 |
| 风控 | 无 | 规则+特征 | 三层融合 |
| 人审中断 | 无 | 无 | interrupt_before |
| 可解释性 | 无 | 规则列表 | 完整决策链 |

---

## Quickstart

```bash
# 1. 克隆
git clone https://github.com/yourname/retailguard-copilot.git
cd retailguard-copilot

# 2. 配置
cp .env.example .env
# 编辑 .env，填入至少一个 LLM API KEY（DEEPSEEK_API_KEY 或 GLM_API_KEY）

# 3. 启动（10 个服务）
docker-compose up -d

# 4. 初始化数据
cd python-impl
python -m scripts.bootstrap

# 5. 访问
open http://localhost
# 登录：customer_a / 123456 / 租户 A
```

### 本地开发

```bash
cd python-impl
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# 跑测试
python -m pytest tests/ -v

# 跑评测
python -m eval.runner --smoke

# MCP 服务器
python -m mcp_tools.mcp_server
```

---

## 项目结构

```
.
├── docs/                      需求 / PRD / 设计 / 升级计划 / 评测报告
├── python-impl/
│   ├── agents/                7 个 Agent 实现 + 3 版本图
│   ├── rag/                   RAG 检索 / Embedding / Rerank
│   ├── risk/                  三层融合风控引擎
│   ├── llm/                   模型路由 + 语义缓存
│   ├── eval/                  5 维度评测体系
│   ├── tasks/                 Celery 异步任务
│   ├── auth/                  JWT + RBAC + 用户服务
│   ├── mcp/                   MCP stdio 服务器
│   ├── api/                   FastAPI 路由
│   ├── db/                    SQLAlchemy 模型 + 多租户
│   ├── tracing/               Langfuse + OTEL
│   ├── exceptions/            ErrorCode 枚举
│   ├── config/                YAML 配置
│   ├── scripts/               bootstrap / generate / check / bench
│   └── tests/                 unit / integration / contract / agent_replay
├── frontend/                  Vue3 + Vite + Element Plus
├── .github/workflows/         ci.yml / eval.yml
└── docker-compose.yml
```

---

## 评测报告

```bash
python -m eval.runner --all --report
# 产出 docs/eval_reports/{date}_{sha}.md
```

| 维度 | 用例数 | 指标 |
|---|---|---|
| Intent | 50 | 准确率 |
| Tool Call | 40 | 调用正确率 |
| RAG | 50 | Top1 命中 + RAGAS |
| Risk | 30 | F1 + FP率 |
| E2E | 30 | 端到端通过率 |

---

## 灰度对比

```bash
python -m eval.runner --version v1,v2,v3 --smoke
# 输出三版本对比表
```

---

## MCP 接入

```bash
# Claude Desktop
claude mcp add retailguard -- python -m mcp_tools.mcp_server

# 或手动配置 claude_desktop_config.json
# 见 docs/mcp_integration.md
```

---

## Roadmap

| 周 | 主题 | 状态 |
|---|---|---|
| W1 | RAG + Knowledge Agent + 多租户 | Done |
| W2 | Eval + Langfuse | Done |
| W3 | Planner + Critic + Interrupt | Done |
| W4 | 三层风控 + 模型路由 + 语义缓存 | Done |
| W5 | Celery + 灰度三版本 + A/B 对比 | Done |
| W6 | JWT + RBAC + 4 角色前端 | Done |
| W7 | Mock 数据 + 性能优化 + 压测 | Done |
| W8 | MCP stdio + CI + 文档 | Done |
| W9 | 演示走查 + 简历定稿 | In Progress |

---

## License

MIT
