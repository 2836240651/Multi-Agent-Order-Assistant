/**
 * 前端 auth store（Vue 3 reactive，无 Pinia 依赖）。
 *
 * 管理 access_token / refresh_token / user 信息，
 * 提供 login / logout / refresh / hasPerm / hasRole 方法。
 */
import { reactive, computed } from "vue";

const STORAGE_KEY = "retailguard_auth";

function _load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function _save(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

function _clear() {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem("staff_token");
  localStorage.removeItem("staff_user");
  localStorage.removeItem("user_id");
}

const _state = reactive({
  accessToken: _load()?.accessToken || "",
  refreshToken: _load()?.refreshToken || "",
  user: _load()?.user || null,
});

export const authStore = {
  // ── 只读状态 ──────────────────────────────────────────────────
  get accessToken() { return _state.accessToken; },
  get refreshToken() { return _state.refreshToken; },
  get user() { return _state.user; },
  get isLoggedIn() { return !!_state.accessToken; },
  get roles() { return _state.user?.roles || []; },
  get permissions() { return _state.user?.permissions || []; },
  get tenantId() { return _state.user?.tenant_id || null; },
  get userId() { return _state.user?.id || null; },

  // ── 默认路由（按角色）─────────────────────────────────────────
  get defaultRoute() {
    const roles = this.roles;
    if (roles.includes("admin")) return "/admin/dashboard";
    if (roles.includes("risk")) return "/risk/reviews";
    if (roles.includes("agent")) return "/agent/dashboard";
    return "/chat";
  },

  // ── 权限检查 ──────────────────────────────────────────────────
  hasPerm(perm) {
    return this.permissions.includes(perm);
  },

  hasRole(role) {
    return this.roles.includes(role);
  },

  // ── 登录 ─────────────────────────────────────────────────────
  setAuth({ accessToken, refreshToken, user }) {
    _state.accessToken = accessToken;
    _state.refreshToken = refreshToken;
    _state.user = user;
    _save({ accessToken, refreshToken, user });

    // 兼容旧代码
    localStorage.setItem("staff_token", accessToken);
    localStorage.setItem("staff_user", JSON.stringify(user));
    localStorage.setItem("user_id", String(user.id));
    localStorage.setItem("tenant_id", String(user.tenant_id));
  },

  // ── 刷新 ─────────────────────────────────────────────────────
  updateAccessToken(newToken) {
    _state.accessToken = newToken;
    _save({ accessToken: newToken, refreshToken: _state.refreshToken, user: _state.user });
    localStorage.setItem("staff_token", newToken);
  },

  // ── 登出 ─────────────────────────────────────────────────────
  clear() {
    _state.accessToken = "";
    _state.refreshToken = "";
    _state.user = null;
    _clear();
  },
};

/**
 * Composable 包装，方便在 setup() 中使用。
 */
export function useAuth() {
  return {
    ...authStore,
    roles: computed(() => authStore.roles),
    permissions: computed(() => authStore.permissions),
    isLoggedIn: computed(() => authStore.isLoggedIn),
  };
}
