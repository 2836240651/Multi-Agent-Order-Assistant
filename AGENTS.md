# RetailGuard Copilot · 项目根 AGENTS.md

> 本文件是项目地图，不是手册。细节按目录渐进披露：每个主目录有自己的 `AGENTS.md`。
> 协作硬规则见 `~/.claude/AGENTS.md`（全局）；本文件只写**本项目特有**的约束。

---

## 1. 项目定位

电商售后多智能体客服系统。技术演进示范型工程作品，目标是把 2026 AI Agent JD 全部硬关键词（RAG / Multi-Agent / Eval / Observability / 灰度 / 风控 / 成本 / 异步 / MCP / 多租户）以**可验证**方式落地。

- 业务侧：4 角色（顾客 / 客服 / 风控 / 管理员）端到端闭环
- 技术侧：7-Agent 协作 + 三层融合风控 + 三版本灰度 + 全链路 trace

详见 `docs/需求.md` / `docs/PRD.md` / `docs/设计.md` / `docs/升级计划.md`。

---

## 2. 技术栈（boring 优先）

后端 Python：FastAPI 0.115+ / LangGraph 0.2+ / PostgreSQL 16 / Redis 7 / Qdrant 1.11 / Celery 5
前端：Vue3 + Vite + Element Plus + Pinia
观测：Langfuse 2.x
对外：MCP Python SDK（stdio）

**禁止引入**：sqlmodel、Pydantic v1、自研 Agent 框架、未在 `docs/设计.md §3` 登记的依赖。

---

## 3. 目录地图

```
.
├── docs/                      需求 / PRD / 设计 / 升级计划 / 评测报告
├── python-impl/
│   ├── agents/                AGENTS.md  ← 7 个 Agent 实现
│   ├── rag/                   AGENTS.md  ← W1 新增：检索/Embedding/Rerank
│   ├── risk/                  AGENTS.md  ← W4 新增：三层融合风控
│   ├── llm/                   AGENTS.md  ← W4 新增：模型路由 + 语义缓存
│   ├── eval/                  AGENTS.md  ← W2 新增：评测体系（注意是 eval，不是 evals）
│   ├── tasks/                 AGENTS.md  ← W5 新增：Celery 异步任务
│   ├── api/                   FastAPI 路由 + 中间件
│   ├── governance/            灰度 / 审计 / 工单状态机
│   ├── memory/                LangGraph state + 历史 long-term store
│   ├── mcp/                   MCP stdio server (W8 重写)
│   ├── tracing/               Langfuse 装饰器
│   ├── exceptions/            ErrorCode 枚举 + 异常基类
│   ├── config/                YAML 配置（风控权重 / 模型路由 / 灰度）
│   └── tests/                 unit / integration / contract / agent_replay
├── frontend/                  AGENTS.md  ← Vue3 工程
├── scripts/                   bootstrap / generate_mock_data / drift_scan / ingest_kb
├── .github/workflows/         ci.yml / eval.yml / drift.yml
└── docker-compose.yml
```

---

## 4. 项目级不变量（机械化校验）

以下每条都对应可执行检查（违反则 pre-commit / CI 失败）：

| 不变量 | 检查脚本 |
|---|---|
| 所有抛出异常必须用 `ErrorCode` 枚举，禁止裸字符串 | `scripts/check_error_code.py` |
| 所有 LLM 调用必须走 `llm.router`，禁止直调 `openai/anthropic/zhipuai/dashscope` 客户端 | `scripts/check_no_direct_llm.py` |
| 业务表查询必须经过 tenant 中间件，禁止显式 `tenant_id == X` 散落（除 `with skip_tenant_filter()` 上下文） | `scripts/check_tenant_filter.py` |
| 每个 `.py` 文件首行 docstring 含中文注释（文件作用） | `scripts/check_file_headers.py` |
| `AGENTS.md` 中列出的子目录必须实际存在；子目录里实际文件必须在该目录 `AGENTS.md` 出现 | `scripts/check_agents_md.py` |
| `requirements.txt` 与代码 `import` 一致 | `scripts/drift_scan.py` |
| 测试覆盖率 ≥ 70% | `pytest --cov-fail-under=70` |

---

## 5. 工作流（与全局 AGENTS.md 衔接）

- **改代码前**：先确认动作在 `docs/升级计划.md` 当前周范围内；越界先在 plan 加条目
- **改代码后**：本目录 `AGENTS.md` 同步更新；前端 `npm run build`；后端 `pytest -x` 至少跑红线测试
- **新增异常**：先补 `exceptions/error_code.py` 枚举，再用
- **新增工具/Agent**：在所属 `AGENTS.md` 登记 + 接 trace
- **review 节点**：每完成一周里程碑提醒用户 review；用户未 review 不进下一周

---

## 6. 命名约定

- 文件夹 / 文件 / 函数：英文 snake_case
- 解释性文档（docs/、AGENTS.md、报告）：中文标题 + 英文标识符
- DB 表 / 字段：英文 snake_case
- 中文注释：每个 `.py` 文件首行 docstring 必含

---

## 7. 快速开始

```bash
cp .env.example .env       # 填模型 KEY
docker-compose up -d
# 等 ~2 min 完成 alembic + mock 灌库
open http://localhost      # demo_customer_1 / 123456 / tenant-a
```

`make` 常用：
- `make eval` — 跑评测，产出 `docs/eval_reports/{date}_{sha}.md`
- `make drift` — 扫描文档/代码漂移
- `make smoke` — 5 分钟 demo 自动化走查

---

## 8. 链路索引

- 业务：`docs/需求.md`
- 界面与流程：`docs/PRD.md`
- 技术架构：`docs/设计.md`
- 9 周节奏：`docs/升级计划.md`
- 协作规则（跨项目）：`~/.claude/AGENTS.md`
- harness 规范源：https://github.com/deusyu/harness-engineering

---

## 9. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-25 | 初版。9 周计划启动，W0 brainstorm 阶段产出 |
