/**
 * API 客户端（axios + JWT 自动注入 + 401 静默 refresh）。
 *
 * - 所有请求自动带 Authorization: Bearer <access_token>
 * - 401 时尝试用 refresh_token 换新 access_token，成功则重试原请求
 * - refresh 失败 → 跳转 /login?redirect_to=当前路径
 */
import axios from "axios";
import { authStore } from "./stores/auth.js";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const http = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// ── 请求拦截：注入 JWT + tenant header ─────────────────────────
http.interceptors.request.use((config) => {
  if (authStore.accessToken) {
    config.headers.Authorization = `Bearer ${authStore.accessToken}`;
  }
  if (authStore.tenantId) {
    config.headers["X-Tenant-Id"] = String(authStore.tenantId);
  }
  return config;
});

// ── 响应拦截：401 → refresh → 重试 ────────────────────────────
let _refreshing = null;

http.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retried) {
      originalRequest._retried = true;

      if (!authStore.refreshToken) {
        _redirectToLogin();
        return Promise.reject(error);
      }

      try {
        if (!_refreshing) {
          _refreshing = _doRefresh();
          const newToken = await _refreshing;
          _refreshing = null;
          authStore.updateAccessToken(newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return http(originalRequest);
        } else {
          const newToken = await _refreshing;
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return http(originalRequest);
        }
      } catch {
        _refreshing = null;
        _redirectToLogin();
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  }
);

async function _doRefresh() {
  const resp = await axios.post(`${API_BASE}/auth/refresh`, {
    refresh_token: authStore.refreshToken,
  });
  return resp.data.access_token;
}

function _redirectToLogin() {
  authStore.clear();
  const redirect = encodeURIComponent(window.location.pathname);
  window.location.href = `/login?redirect_to=${redirect}`;
}

// ── 导出 ──────────────────────────────────────────────────────

export const api = {
  // Auth
  login(username, password, tenantId) {
    return http.post("/auth/login", { username, password, tenant_id: tenantId });
  },
  me() {
    return http.get("/auth/me");
  },
  logout() {
    return http.post("/auth/logout");
  },

  // Chat (SSE 需要单独处理，不走 axios)
  chat(payload) {
    return http.post("/api/v1/chat", payload, { responseType: "stream" });
  },

  // Tasks
  batchReview(ticketIds) {
    return http.post("/api/v1/tasks/batch_review", { ticket_ids: ticketIds });
  },
  taskProgress(taskId) {
    return http.get(`/api/v1/tasks/${taskId}/progress`);
  },

  // Admin
  cost(groupBy = "model") {
    return http.get("/api/v1/admin/cost", { params: { group_by: groupBy } });
  },
  capabilities() {
    return http.get("/api/v1/admin/capabilities");
  },
  getRollout() {
    return http.get("/api/v1/admin/rollout");
  },
  updateRollout(weights) {
    return http.put("/api/v1/admin/rollout", weights);
  },
  rolloutAudit(limit = 20) {
    return http.get("/api/v1/admin/rollout/audit", { params: { limit } });
  },
  listTenants() {
    return http.get("/api/v1/admin/tenants");
  },
  createTenant(code, name) {
    return http.post("/api/v1/admin/tenants", { code, name });
  },

  // Review
  reviewResume(threadId, action, reviewerNote = "") {
    return http.post(`/api/v1/review/${threadId}/resume`, {
      action,
      reviewer_note: reviewerNote,
    });
  },
  reviewQueue(params = {}) {
    return http.get("/api/v1/review/queue", { params });
  },

  // Orders
  listOrders(params = {}) {
    return http.get("/api/v1/orders", { params });
  },
  getOrder(orderNo) {
    return http.get(`/api/v1/orders/${orderNo}`);
  },

  // Tickets
  listTickets(params = {}) {
    return http.get("/api/v1/tickets", { params });
  },
  getTicket(ticketNo) {
    return http.get(`/api/v1/tickets/${ticketNo}`);
  },
  ticketAction(ticketNo, action, note = "") {
    return http.post(`/api/v1/tickets/${ticketNo}/actions`, { action, note });
  },

  // Refunds
  createRefund(data) {
    return http.post("/api/v1/refunds", data);
  },
  listRefunds(params = {}) {
    return http.get("/api/v1/refunds", { params });
  },
  getRefund(refundNo) {
    return http.get(`/api/v1/refunds/${refundNo}`);
  },
  reviewRefund(refundNo, action, note = "") {
    return http.post(`/api/v1/refunds/${refundNo}/review`, { action, note });
  },

  // Threads
  listThreads() {
    return http.get("/api/v1/threads");
  },
  getThreadMessages(threadId, limit = 50) {
    return http.get(`/api/v1/threads/${threadId}/messages`, { params: { limit } });
  },

  // Health
  health() {
    return http.get("/health");
  },
};

export { http };
