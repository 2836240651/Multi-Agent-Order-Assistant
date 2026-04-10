<script setup>
import { ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import ToastNotification from "./components/ToastNotification.vue";

const route = useRoute();
const router = useRouter();
const isSidebarCollapsed = ref(false);
const isDarkMode = ref(false);

const isLoggedIn = () => !!localStorage.getItem("staff_token") || !!localStorage.getItem("user_id");

const showSidebar = computed(() => {
  return !['/login', '/user', '/staff-login'].includes(route.path) && isLoggedIn();
});
const isStaffLoggedIn = computed(() => !!localStorage.getItem("staff_token"));
const staffUser = computed(() => {
  const user = localStorage.getItem("staff_user");
  return user ? JSON.parse(user) : null;
});

const navItems = [
  { path: "/dashboard", name: "首页概览", icon: "🏠" },
  { path: "/chat", name: "对话控制台", icon: "💬" },
  { path: "/reviews", name: "人工复核", icon: "🔍" },
  { path: "/audit", name: "审计日志", icon: "📋" },
  { path: "/ops", name: "运维管理", icon: "⚙️" },
];

const currentPath = computed(() => route.path);

function navigate(path) {
  router.push(path);
}

function toggleDarkMode() {
  isDarkMode.value = !isDarkMode.value;
  document.documentElement.setAttribute("data-theme", isDarkMode.value ? "dark" : "light");
}

function logout() {
  localStorage.removeItem("staff_token");
  localStorage.removeItem("staff_user");
  router.push("/staff-login");
}

function goToUserPortal() {
  router.push("/login");
}
</script>

<template>
  <div class="app-shell" :class="{ dark: isDarkMode }">
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
        <div v-if="!isSidebarCollapsed && isStaffLoggedIn" class="staff-info">
          <span class="staff-name">{{ staffUser?.username || 'Staff' }}</span>
        </div>
        <button v-if="!isSidebarCollapsed" class="theme-toggle" @click="toggleDarkMode">
          {{ isDarkMode ? "☀️ 浅色" : "🌙 深色" }}
        </button>
        <button v-if="!isSidebarCollapsed" class="logout-btn" @click="logout">
          登出
        </button>
        <button v-if="!isSidebarCollapsed" class="user-portal-btn" @click="goToUserPortal">
          用户入口
        </button>
        <span v-if="!isSidebarCollapsed" class="version">v1.3.0</span>
      </div>
    </aside>

    <main class="main-content" :class="{ 'full-width': !showSidebar }">
      <router-view />
    </main>

    <ToastNotification />
  </div>
</template>

<style scoped>
.full-width {
  width: 100%;
}
</style>

<style scoped>
.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid rgba(255,255,255,0.1);
}

.staff-info {
  text-align: center;
  padding: 4px 0;
}

.staff-name {
  font-size: 12px;
  color: #a0a0a0;
}

.logout-btn, .user-portal-btn {
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

.logout-btn:hover, .user-portal-btn:hover {
  background: rgba(255,255,255,0.2);
  color: white;
}

.user-portal-btn {
  border-color: #667eea;
  color: #667eea;
}

.user-portal-btn:hover {
  background: #667eea;
  color: white;
}
</style>
