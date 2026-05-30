/**
 * v-permission 指令：按权限或角色控制元素显隐。
 *
 * 用法：
 *   <button v-permission="'admin:rollout'">调整灰度</button>
 *   <div v-permission="['admin:rollout', 'admin:cost']">管理员面板</div>
 *   <span v-permission.role="'risk'">风控专属</span>
 *
 * 权限不足时元素从 DOM 移除（v-if 语义）。
 */
import { authStore } from "../stores/auth.js";

function _check(el, binding) {
  const value = binding.value;
  const isRole = binding.modifiers?.role;

  if (!value) return;

  const items = Array.isArray(value) ? value : [value];
  const checker = isRole ? authStore.hasRole.bind(authStore) : authStore.hasPerm.bind(authStore);

  const hasAccess = items.some((item) => checker(item));

  if (!hasAccess) {
    el.parentNode?.removeChild(el);
  }
}

export const permissionDirective = {
  mounted: _check,
  updated: _check,
};

export const roleDirective = {
  mounted(el, binding) {
    _check(el, { ...binding, modifiers: { role: true } });
  },
  updated(el, binding) {
    _check(el, { ...binding, modifiers: { role: true } });
  },
};
