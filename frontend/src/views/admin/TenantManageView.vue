<script setup>
/**
 * 管理员视图：租户管理（列表 + 创建）。
 */
import { ref, onMounted } from "vue";
import { api } from "../../api.js";

const tenants = ref([]);
const newCode = ref("");
const newName = ref("");
const creating = ref(false);

async function load() {
  try {
    const resp = await api.listTenants();
    tenants.value = resp.data.tenants || [];
  } catch {}
}

async function create() {
  if (!newCode.value || !newName.value) return;
  creating.value = true;
  try {
    await api.createTenant(newCode.value, newName.value);
    newCode.value = "";
    newName.value = "";
    await load();
  } catch (e) {
    alert("创建失败: " + (e.response?.data?.message || e.message));
  } finally {
    creating.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="tenant-manage">
    <header class="page-header">
      <h1>租户管理</h1>
      <span class="count">{{ tenants.length }} 个租户</span>
    </header>

    <section class="create-section">
      <h2>新建租户</h2>
      <div class="create-form">
        <input v-model="newCode" placeholder="code（如 tenant-f）" maxlength="50" />
        <input v-model="newName" placeholder="名称（如 数码电器F）" maxlength="100" />
        <button class="btn-create" @click="create" :disabled="creating || !newCode || !newName">
          {{ creating ? "创建中..." : "创建" }}
        </button>
      </div>
    </section>

    <section class="list-section">
      <h2>租户列表</h2>
      <table class="tenant-table">
        <thead>
          <tr><th>ID</th><th>Code</th><th>名称</th><th>创建时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="t in tenants" :key="t.id">
            <td>{{ t.id }}</td>
            <td><code>{{ t.code }}</code></td>
            <td>{{ t.name }}</td>
            <td>{{ t.created_at }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="tenants.length === 0" class="empty">暂无租户数据（运行 bootstrap.py 初始化）</div>
    </section>
  </div>
</template>

<style scoped>
.tenant-manage { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 22px; margin: 0; }
.count { color: #888; font-size: 14px; }
.create-section { background: #fff; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
.create-section h2 { font-size: 16px; margin: 0 0 12px; }
.create-form { display: flex; gap: 8px; }
.create-form input { flex: 1; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
.btn-create { padding: 8px 20px; background: #667eea; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
.btn-create:disabled { opacity: 0.5; cursor: not-allowed; }
.list-section { background: #fff; border-radius: 10px; padding: 20px; }
.list-section h2 { font-size: 16px; margin: 0 0 12px; }
.tenant-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.tenant-table th, .tenant-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }
.empty { text-align: center; color: #ccc; padding: 40px; }
</style>
