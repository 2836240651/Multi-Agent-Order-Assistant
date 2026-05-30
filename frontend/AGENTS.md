# frontend/ · Vue3 工程 AGENTS.md

> 4 角色统一前端。W6 完成 JWT + RBAC + 多租户改造。

---

## 1. 目录结构

```
src/
├── views/          路由视图（按角色组织）
├── components/     可复用组件
├── composables/    组合式 API（useAuth / useTenant / usePermission / useSse）
├── router/         路由 + 权限守卫
├── api.js          统一封装（axios + interceptors）
├── styles.css      全局样式 token
└── main.js
```

视图清单（W6 整理后）：

| 角色 | View 文件 |
|---|---|
| 公共 | `LoginView.vue` |
| 顾客 | `ChatView.vue` / `OrderListView.vue` / `TicketDetailView.vue` / `RefundFormView.vue` |
| 客服 | `AgentDashboardView.vue` / `SessionInboxView.vue` / `ConversationView.vue`（`/agent/conversation/:threadId`）/ `TicketHandleView.vue` |
| 风控 | `ReviewQueueView.vue` / `RiskDecisionView.vue` |
| 管理员 | `AdminDashboardView.vue` / `RolloutView.vue` / `TenantManageView.vue` / `CostView.vue` / `TraceView.vue` |

**注意**：旧 `UserDashboardView` / `AuditView` / `OpsView` 已移除，路由重定向至 `/chat`、`/risk/reviews`、`/admin/dashboard`。

---

## 2. 不变量

- 所有 API 通过 `src/api.js` 走，禁直 `fetch` / 裸 `axios`
- 每个写按钮绑定 `v-permission="perm:code"`，无权限不渲染
- `axios` 拦截器自动带 `Authorization` + `X-Tenant-Id`
- 401 → 静默 refresh；refresh 失败 → 跳 `/login?redirect_to=...`
- 跨租户错误（实际返 404）也跳列表页 + toast"未找到"
- 每次改 `.vue` 后必须 `npm run build` 通过（pre-commit 集成）

---

## 3. 流式

- 聊天用 `EventSource`（SSE）；接 `/api/v1/chat`
- 任务进度用 `WebSocket`（`/ws/tasks/{id}`），断线 5s 重连
- 流式中止：保存 `AbortController`，UI 提供"中止"按钮

---

## 4. UI 基准

- 组件库：Element Plus 2.x，主色 `#409EFF`
- 设计稿：本项目不做高保真 UI 稿，wireframe 见 `docs/PRD.md §4`
- **改 UI 基准（设计 token / 全局样式）前必须先开研讨会**（对齐 `~/.claude/AGENTS.md §3`）

---

## 5. 测试

- 关键路径用 Cypress E2E（W8 覆盖 12 条演示主线）
- 组件单测 Vitest（仅核心：v-permission / api 拦截器 / SSE composable）

---

## 6. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-25 | 占位，W6 角色重组与权限改造 |
