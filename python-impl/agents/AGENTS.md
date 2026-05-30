# agents/ · Agent 实现层 AGENTS.md

> 7-Agent 协作拓扑的代码归宿。整体拓扑见 `docs/设计.md §6.1`，状态字段见 §6.2。

---

## 1. 职责边界

| Agent | 单一职责 | 调用模型 profile | 文件 |
|---|---|---|---|
| supervisor | StateGraph 入口 + 整体路由 + 终态判定 | — | `supervisor.py` |
| intent_router | NLU 意图 + 复杂度估算（含语义缓存） | light | `intent_router.py` |
| greeting_handler | 闲聊 / 寒暄兜底（@observe 已接入） | light | `greeting_handler.py` |
| knowledge_agent | RAG 检索 + 引用答案（含语义缓存） | medium | `knowledge_agent.py` |
| planner | 多步骤拆解（Pydantic 强约束） | heavy | `planner.py`（W3 新增） |
| critic | 输出交叉校验 / approve-revise-escalate | heavy | `critic.py`（W3 新增） |
| plan_executor | 执行 Planner 生成的步骤（mock 工具） | — | `plan_executor.py`（W3 新增） |
| risk_review | 三层融合风控（薄壳调 risk.evaluate） | — | `risk_review.py` |

---

## 2. 三版本切换

`versions/` 子目录承载三个独立 build 函数（W5）：
- `v1.py` — 单 Agent + 关键词查询
- `v2.py` — 单 Agent + 工具 + 规则风控
- `v3.py` — 全 7 Agent + 三层风控 + Planner + Critic + RAG

入口 `GRAPHS = {"v1": ..., "v2": ..., "v3": ...}`；外层 Gateway 通过 `llm.router` + RolloutManager 决策版本。

---

## 3. 不变量

- 每个 Agent 文件首行 docstring 含中文，说明输入/输出/对应 design 章节
- Agent 之间**禁止互 import**；通信只通过 `AgentState`
- 任何 LLM 调用必须 `from llm.router import call_llm(profile=...)`，禁直调原生 SDK
- 节点函数包 `@observe(name="...")` 接 Langfuse
- 抛异常用 `ErrorCode` 枚举，禁裸字符串

---

## 4. AgentState 改动规则

字段定义在 `agents/state.py`。新增字段必须：
1. 在 `docs/设计.md §6.2` 同步追加
2. 给出默认值（避免下游 KeyError）
3. 序列化到 PG Checkpoint 时无大对象（>1MB 拆出存外）

---

## 5. 测试入口

- `tests/unit/agents/` — 单 Agent 输入/输出（用 mock LLM）
- `tests/agent_replay/` — fixture 回放完整 graph（每个 PR 跑）

---

## 6. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-27 | W4 补完：semantic_cache 接入 knowledge_agent + intent_router；greeting_handler 接 @observe；v2 版本 risk_lite 节点接入图；rollout.decide() 改确定性 hash；AGENTS.md 同步删除已废弃文件（compliance_checker、ticket_handler、knowledge_rag） |
| 2026-05-26 | W3 完成：planner.py + critic.py + plan_executor.py + risk_review.py；supervisor 升级 7 节点图 + MemorySaver/AsyncPostgresSaver checkpoint；interrupt_before=["risk_review"]；/api/v1/review/{thread_id}/resume；33 条测试全绿 |
| 2026-05-25 | 初版。登记现有 5 个 Agent + W3 新增 planner/critic + W5 新增 versions/ |
