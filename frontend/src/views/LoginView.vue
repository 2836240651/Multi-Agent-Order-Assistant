<script setup>
/**
 * 登录页：统一 JWT 登录，登录后按角色跳转默认页。
 */
import { ref, reactive } from "vue";
import { useRouter, useRoute } from "vue-router";
import { api } from "../api.js";
import { authStore } from "../stores/auth.js";

const router = useRouter();
const route = useRoute();
const isLoading = ref(false);
const errorMsg = ref("");

const form = reactive({
  username: "",
  password: "",
  tenant_id: 1,
});

const TENANTS = [
  { id: 1, name: "优选商城（A）" },
  { id: 2, name: "科技直营（B）" },
  { id: 3, name: "时尚穿搭（C）" },
  { id: 4, name: "数码电器（D）" },
  { id: 5, name: "居家生活（E）" },
];

async function handleLogin() {
  errorMsg.value = "";
  isLoading.value = true;

  try {
    const resp = await api.login(form.username, form.password, form.tenant_id);
    const data = resp.data;

    authStore.setAuth({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user: { ...data.user, tenant_id: form.tenant_id, permissions: [] },
    });

    // 先拿 /auth/me 补全 permissions
    try {
      const meResp = await api.me();
      authStore.setAuth({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: { ...meResp.data },
      });
    } catch {}

    const redirect = route.query.redirect_to;
    router.push(redirect || authStore.defaultRoute);
  } catch (e) {
    const msg = e.response?.data?.message || e.message;
    errorMsg.value = msg || "登录失败，请检查账号密码";
  } finally {
    isLoading.value = false;
  }
}

// 快速填入 demo 账号
function fillDemo(role) {
  const suffix = "a";
  form.username = `${role}_${suffix}`;
  form.password = "123456";
  form.tenant_id = 1;
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="logo-icon">🛡️</div>
        <h1>RetailGuard</h1>
        <p>智能售后客服系统</p>
      </div>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label>租户</label>
          <select v-model.number="form.tenant_id">
            <option v-for="t in TENANTS" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>

        <div class="form-group">
          <label>用户名</label>
          <input v-model="form.username" type="text" placeholder="如 customer_a" autocomplete="username" />
        </div>

        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="默认 123456" autocomplete="current-password" />
        </div>

        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <button type="submit" class="submit-btn" :disabled="isLoading">
          <span v-if="isLoading" class="loading-spinner"></span>
          {{ isLoading ? "登录中..." : "登录" }}
        </button>
      </form>

      <div class="demo-accounts">
        <span class="demo-label">快速登录：</span>
        <button class="demo-btn" @click="fillDemo('customer')">顾客</button>
        <button class="demo-btn" @click="fillDemo('agent')">客服</button>
        <button class="demo-btn" @click="fillDemo('risk')">风控</button>
        <button class="demo-btn" @click="fillDemo('admin')">管理员</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}
.login-card {
  background: white;
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}
.login-header { text-align: center; margin-bottom: 32px; }
.logo-icon { font-size: 48px; margin-bottom: 12px; }
.login-header h1 { font-size: 28px; color: #333; margin: 0 0 8px; }
.login-header p { color: #666; margin: 0; font-size: 14px; }
.login-form { display: flex; flex-direction: column; gap: 18px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 14px; color: #333; font-weight: 500; }
.form-group input, .form-group select {
  padding: 12px 16px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px;
  transition: border-color 0.3s;
}
.form-group input:focus, .form-group select:focus { outline: none; border-color: #667eea; }
.error-msg { color: #e74c3c; font-size: 14px; text-align: center; padding: 8px; background: #fde8e8; border-radius: 6px; }
.submit-btn {
  padding: 14px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 500;
  cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;
}
.submit-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4); }
.submit-btn:disabled { opacity: 0.7; cursor: not-allowed; }
.loading-spinner { width: 16px; height: 16px; border: 2px solid white; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.demo-accounts { margin-top: 20px; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; flex-wrap: wrap; }
.demo-label { font-size: 13px; color: #999; }
.demo-btn { padding: 4px 10px; border: 1px solid #ddd; background: #f8f9fa; border-radius: 4px; cursor: pointer; font-size: 12px; }
.demo-btn:hover { background: #667eea; color: #fff; border-color: #667eea; }
</style>
