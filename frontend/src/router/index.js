/**
 * 路由配置：4 角色（customer / agent / risk / admin）视图 + 权限守卫。
 *
 * meta.requiresAuth — 需要登录
 * meta.roles — 允许的角色列表（不设则所有登录用户可访问）
 */
import { createRouter, createWebHistory } from "vue-router";
import { authStore } from "../stores/auth.js";

// ── 视图（懒加载）──────────────────────────────────────────────

// 公共
const LoginView = () => import("../views/LoginView.vue");

// 顾客
const ChatView = () => import("../views/ChatView.vue");
const OrderListView = () => import("../views/OrderListView.vue");
const TicketDetailView = () => import("../views/TicketDetailView.vue");
const RefundFormView = () => import("../views/RefundFormView.vue");
const AddressChangeView = () => import("../views/AddressChangeView.vue");

// 客服
const AgentDashboardView = () => import("../views/agent/AgentDashboardView.vue");
const SessionInboxView = () => import("../views/agent/SessionInboxView.vue");
const ConversationView = () => import("../views/agent/ConversationView.vue");
const TicketHandleView = () => import("../views/agent/TicketHandleView.vue");

// 风控
const ReviewQueueView = () => import("../views/risk/ReviewQueueView.vue");
const RiskDecisionView = () => import("../views/risk/RiskDecisionView.vue");

// 管理员
const AdminDashboardView = () => import("../views/admin/AdminDashboardView.vue");
const RolloutView = () => import("../views/admin/RolloutView.vue");
const TenantManageView = () => import("../views/admin/TenantManageView.vue");
const CostView = () => import("../views/admin/CostView.vue");
const TraceView = () => import("../views/admin/TraceView.vue");
const AdminCapabilitiesView = () => import("../views/admin/AdminCapabilitiesView.vue");

// 兼容旧路由（重定向）
const StaffLoginView = () => import("../views/StaffLoginView.vue");

// ── 路由表 ─────────────────────────────────────────────────────

const routes = [
  // 公共
  { path: "/", redirect: "/login" },
  { path: "/login", name: "Login", component: LoginView },
  { path: "/staff-login", name: "StaffLogin", component: StaffLoginView },

  // 顾客
  {
    path: "/chat",
    name: "Chat",
    component: ChatView,
    meta: { requiresAuth: true, roles: ["customer", "agent", "admin"] },
  },
  {
    path: "/orders",
    name: "OrderList",
    component: OrderListView,
    meta: { requiresAuth: true, roles: ["customer", "agent", "admin"] },
  },
  {
    path: "/orders/:orderNo",
    name: "OrderDetail",
    component: TicketDetailView,
    meta: { requiresAuth: true, roles: ["customer", "agent", "admin"] },
  },
  {
    path: "/refund",
    name: "RefundForm",
    component: RefundFormView,
    meta: { requiresAuth: true, roles: ["customer", "admin"] },
  },
  {
    path: "/address-change",
    name: "AddressChange",
    component: AddressChangeView,
    meta: { requiresAuth: true, roles: ["customer", "agent", "admin"] },
  },

  // 客服
  {
    path: "/agent/dashboard",
    name: "AgentDashboard",
    component: AgentDashboardView,
    meta: { requiresAuth: true, roles: ["agent", "admin"] },
  },
  {
    path: "/agent/sessions",
    name: "SessionInbox",
    component: SessionInboxView,
    meta: { requiresAuth: true, roles: ["agent", "admin"] },
  },
  {
    path: "/agent/conversation/:threadId",
    name: "Conversation",
    component: ConversationView,
    meta: { requiresAuth: true, roles: ["agent", "admin"] },
  },
  {
    path: "/agent/tickets/:ticketNo",
    name: "TicketHandle",
    component: TicketHandleView,
    meta: { requiresAuth: true, roles: ["agent", "admin"] },
  },

  // 风控
  {
    path: "/risk/reviews",
    name: "ReviewQueue",
    component: ReviewQueueView,
    meta: { requiresAuth: true, roles: ["risk", "admin"] },
  },
  {
    path: "/risk/decision/:refundNo",
    name: "RiskDecision",
    component: RiskDecisionView,
    meta: { requiresAuth: true, roles: ["risk", "admin"] },
  },

  // 管理员
  {
    path: "/admin/dashboard",
    name: "AdminDashboard",
    component: AdminDashboardView,
    meta: { requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/rollout",
    name: "Rollout",
    component: RolloutView,
    meta: { requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/tenants",
    name: "TenantManage",
    component: TenantManageView,
    meta: { requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/cost",
    name: "Cost",
    component: CostView,
    meta: { requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/traces",
    name: "TraceView",
    component: TraceView,
    meta: { requiresAuth: true, roles: ["admin"] },
  },
  {
    path: "/admin/capabilities",
    name: "AdminCapabilities",
    component: AdminCapabilitiesView,
    meta: { requiresAuth: true, roles: ["admin"] },
  },

  // 兼容旧路由（重定向）
  { path: "/user", redirect: "/chat" },
  { path: "/dashboard", redirect: "/admin/dashboard" },
  { path: "/reviews", redirect: "/risk/reviews" },
  { path: "/audit", redirect: "/risk/reviews" },
  { path: "/ops", redirect: "/admin/dashboard" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// ── 守卫 ───────────────────────────────────────────────────────

router.beforeEach((to, from, next) => {
  if (!to.meta.requiresAuth) {
    next();
    return;
  }

  if (!authStore.isLoggedIn) {
    next({ path: "/login", query: { redirect_to: to.fullPath } });
    return;
  }

  const allowedRoles = to.meta.roles;
  if (allowedRoles && !allowedRoles.some((r) => authStore.hasRole(r))) {
    // 角色不足 → 跳默认页
    next(authStore.defaultRoute);
    return;
  }

  next();
});

export default router;
