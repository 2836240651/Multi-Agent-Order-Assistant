# RetailGuard Copilot · 简历项目段落（定稿草稿）

## 项目名称

RetailGuard Copilot — 企业级电商售后多智能体客服（LangGraph + RAG + 三层风控）

## Highlights（投递用 5–6 条）

1. 设计并实现 **7-Agent LangGraph** 协作拓扑（意图路由 / RAG / Planner-Critic / 三层风控 / 人审 Interrupt），支持 PG Checkpoint 断点续跑。
2. 落地 **混合检索 RAG**（BM25 + 向量 RRF + Rerank），端到端 SSE 流式答案与可点击引用；评测集 200 条、`make eval-smoke` 自动化。
3. 构建 **三层融合风控**（规则 + 特征 + LLM），可解释决策链与风控队列前端；融合阈值可配置。
4. 实现 **JWT + RBAC + 多租户**（4 角色、按钮级 `v-permission`），跨租户访问 404 防枚举。
5. 完成 **灰度三版本**（v1/v2/v3）与 `make eval-ab` A/B 对比；Celery 异步任务与 Docker 全栈一键部署。
6. 提供 **MCP stdio** 对外 4 工具，配套 CI（ruff / pytest≥70% / eval smoke）与 Langfuse 全链路观测。

## 技术栈

Python 3.12 · FastAPI · LangGraph · PostgreSQL · Redis · Qdrant · Vue3 · Celery · Langfuse · MCP

## 仓库链接

（填写 GitHub URL）

## 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-05-30 | W9 简历定稿草稿 |
