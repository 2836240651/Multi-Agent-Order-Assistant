import { createRouter, createWebHistory } from "vue-router";
import DashboardView from "../views/DashboardView.vue";
import ChatView from "../views/ChatView.vue";
import ReviewView from "../views/ReviewView.vue";
import AuditView from "../views/AuditView.vue";
import OpsView from "../views/OpsView.vue";
import LoginView from "../views/LoginView.vue";
import UserDashboardView from "../views/UserDashboardView.vue";
import StaffLoginView from "../views/StaffLoginView.vue";

function isLoggedIn() {
  return !!localStorage.getItem("staff_token") || !!localStorage.getItem("user_id");
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/login",
    },
    {
      path: "/login",
      name: "Login",
      component: LoginView,
    },
    {
      path: "/staff-login",
      name: "StaffLogin",
      component: StaffLoginView,
    },
    {
      path: "/user",
      name: "User",
      component: UserDashboardView,
    },
    {
      path: "/dashboard",
      name: "Dashboard",
      component: DashboardView,
      meta: { requiresAuth: true },
    },
    {
      path: "/chat",
      name: "Chat",
      component: ChatView,
      meta: { requiresAuth: true },
    },
    {
      path: "/reviews",
      name: "Reviews",
      component: ReviewView,
      meta: { requiresAuth: true },
    },
    {
      path: "/audit",
      name: "Audit",
      component: AuditView,
      meta: { requiresAuth: true },
    },
    {
      path: "/ops",
      name: "Ops",
      component: OpsView,
      meta: { requiresAuth: true },
    },
  ],
});

router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth && !isLoggedIn()) {
    next("/staff-login");
  } else {
    next();
  }
});

export default router;