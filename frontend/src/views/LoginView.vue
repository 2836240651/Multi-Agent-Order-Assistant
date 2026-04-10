<script setup>
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const isLogin = ref(true);
const isLoading = ref(false);
const showSuccessModal = ref(false);
const successMessage = ref("");

const form = reactive({
  user_id: "",
  email: "",
  password: "",
});

const errorMsg = ref("");

async function handleSubmit() {
  errorMsg.value = "";
  isLoading.value = true;

  try {
    if (isLogin.value) {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: form.email, password: form.password }),
      });
      const data = await res.json();
      if (!res.ok) {
        errorMsg.value = data.detail || "登录失败";
      } else {
        localStorage.setItem("user", JSON.stringify(data.user));
        localStorage.setItem("user_id", data.user.user_id);
        showSuccessModal.value = true;
        successMessage.value = "登录成功！正在跳转...";
        setTimeout(() => {
          router.push("/user");
        }, 1500);
      }
    } else {
      if (!form.user_id || !form.email || !form.password) {
        errorMsg.value = "请填写所有字段";
        isLoading.value = false;
        return;
      }
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: form.user_id,
          email: form.email,
          password: form.password,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        errorMsg.value = data.detail || "注册失败";
      } else {
        showSuccessModal.value = true;
        successMessage.value = "注册成功！请登录";
        setTimeout(() => {
          showSuccessModal.value = false;
          isLogin.value = true;
          form.user_id = "";
          form.email = "";
          form.password = "";
        }, 2000);
      }
    }
  } catch (e) {
    errorMsg.value = "网络错误，请重试";
  }
  isLoading.value = false;
}

function toggleMode() {
  isLogin.value = !isLogin.value;
  errorMsg.value = "";
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="logo-icon">🛡️</div>
        <h1>RetailGuard</h1>
        <p>{{ isLogin ? "欢迎回来" : "创建账号" }}</p>
      </div>

      <form @submit.prevent="handleSubmit" class="login-form">
        <div v-if="!isLogin" class="form-group">
          <label>用户ID</label>
          <input
            v-model="form.user_id"
            type="text"
            placeholder="请输入用户ID（如 user_0003）"
            autocomplete="username"
          />
          <span class="hint">用户ID为您的会员编号，格式为 user_数字</span>
        </div>

        <div class="form-group">
          <label>邮箱</label>
          <input
            v-model="form.email"
            type="email"
            placeholder="请输入邮箱"
            autocomplete="email"
          />
        </div>

        <div class="form-group">
          <label>密码</label>
          <input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
          />
        </div>

        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>

        <button type="submit" class="submit-btn" :disabled="isLoading">
          <span v-if="isLoading" class="loading-spinner"></span>
          {{ isLoading ? "处理中..." : (isLogin ? "登录" : "注册") }}
        </button>
      </form>

      <div class="login-footer">
        <a href="#" @click.prevent="toggleMode">
          {{ isLogin ? "没有账号？立即注册" : "已有账号？去登录" }}
        </a>
        <div class="staff-link">
          <router-link to="/staff-login">员工登录入口</router-link>
        </div>
      </div>
    </div>

    <div v-if="showSuccessModal" class="modal-overlay">
      <div class="modal-content success-modal">
        <div class="success-icon">✓</div>
        <p>{{ successMessage }}</p>
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
  max-width: 400px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.login-header h1 {
  font-size: 28px;
  color: #333;
  margin: 0 0 8px 0;
}

.login-header p {
  color: #666;
  margin: 0;
  font-size: 14px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

.form-group input {
  padding: 12px 16px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  transition: border-color 0.3s;
}

.form-group input:focus {
  outline: none;
  border-color: #667eea;
}

.hint {
  font-size: 12px;
  color: #999;
}

.error-msg {
  color: #e74c3c;
  font-size: 14px;
  text-align: center;
  padding: 8px;
  background: #fde8e8;
  border-radius: 6px;
}

.submit-btn {
  padding: 14px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid white;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-footer {
  margin-top: 24px;
  text-align: center;
}

.login-footer a {
  color: #667eea;
  text-decoration: none;
  font-size: 14px;
}

.login-footer a:hover {
  text-decoration: underline;
}

.staff-link {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #eee;
}

.staff-link a {
  color: #666;
  font-size: 13px;
}

.staff-link a:hover {
  color: #333;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.success-modal {
  background: white;
  border-radius: 16px;
  padding: 40px;
  text-align: center;
  animation: modalIn 0.3s ease;
}

@keyframes modalIn {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.success-icon {
  width: 60px;
  height: 60px;
  background: #27ae60;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  margin: 0 auto 16px;
}

.success-modal p {
  font-size: 16px;
  color: #333;
  margin: 0;
}
</style>
