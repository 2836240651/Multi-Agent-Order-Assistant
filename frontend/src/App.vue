<script setup>
/**
 * App shell：角色感知侧边栏 + 路由出口。
 *
 * 侧边栏导航项按当前用户角色动态过滤。
 */
import { ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { authStore } from "./stores/auth.js";
import ToastNotification from "./components/ToastNotification.vue";

const route = useRoute();
const router = useRouter();
const isSidebarCollapsed = ref(false);

const showSidebar = computed(() => {
  return !["/login", "/staff-login"].includes(route.path) && authStore.isLoggedIn;
});

// 按角色生成导航项
const navItems = computed(() => {
  const items = [];
  const roles = authStore.roles;

  if (roles.includes("admin")) {
    items.push(
      { path: "/admin/dashboard", name: "管理概览", icon: "🏠" },
      { path: "/admin/rollout", name: "灰度管理", icon: "🎯" },
      { path: "/admin/tenants", name: "租户管理", icon: "🏢" },
      { path: "/admin/cost", name: "成本面板", icon: "💰" },
      { path: "/admin/traces", name: "Trace 查看", icon: "🔬" },
    );
  }

  if (roles.includes("risk") || roles.includes("admin")) {
    items.push({ path: "/risk/reviews", name: "风控审核", icon: "🔍" });
  }

  if (roles.includes("agent") || roles.includes("admin")) {
    items.push(
      { path: "/agent/dashboard", name: "客服工作台", icon: "📋" },
      { path: "/agent/sessions", name: "会话收件箱", icon: "📬" },
    );
  }

  if (roles.includes("customer") || roles.includes("agent") || roles.includes("admin")) {
    items.push(
      { path: "/chat", name: "对话控制台", icon: "💬" },
      { path: "/orders", name: "订单列表", icon: "📦" },
    );
  }

  return items;
});

const currentPath = computed(() => route.path);

function navigate(path) {
  router.push(path);
}

function logout() {
  authStore.clear();
  router.push("/login");
}
</script>

<template>
  <div class="app-shell">
    <aside v-if="showSidebar" class="sidebar" :class="{ collapsed: isSidebarCollapsed }">
      <div class="sidebar-header">
        <div class="logo">
          <span class="logo-icon">🛡️</span>
          <span v-if="!isSidebarCollapsed" class="logo-text">RetailGuard</span>
        </div>
        <button class="collapse-btn" @click="isSidebarCollapsed = !isSidebarCollapsed">
          {{ isSidebarCollapsed ? "→" : "←" }}
        </button>
      </div>

      <nav class="sidebar-nav">
        <button
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: currentPath === item.path }"
          @click="navigate(item.path)"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span v-if="!isSidebarCollapsed" class="nav-text">{{ item.name }}</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div v-if="!isSidebarCollapsed" class="user-info">
          <span class="user-name">{{ authStore.user?.display_name || '用户' }}</span>
          <span class="user-roles">{{ authStore.roles.join(', ') }}</span>
        </div>
        <button v-if="!isSidebarCollapsed" class="logout-btn" @click="logout">登出</button>
        <span v-if="!isSidebarCollapsed" class="version">v2.0.0</span>
      </div>
    </aside>

    <main class="main-content" :class="{ 'full-width': !showSidebar }">
      <router-view />
    </main>

    <ToastNotification />
  </div>
</template>

<style scoped>
.full-width { width: 100%; }
.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid rgba(255,255,255,0.1);
}
.user-info { text-align: center; padding: 4px 0; }
.user-name { display: block; font-size: 13px; color: #ddd; font-weight: 600; }
.user-roles { display: block; font-size: 11px; color: #888; }
.logout-btn {
  width: 100%;
  padding: 8px;
  border: 1px solid rgba(255,255,255,0.2);
  background: rgba(255,255,255,0.1);
  color: #ccc;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}
.logout-btn:hover { background: rgba(255,255,255,0.2); color: white; }
.version { text-align: center; font-size: 11px; color: #555; }
</style>
