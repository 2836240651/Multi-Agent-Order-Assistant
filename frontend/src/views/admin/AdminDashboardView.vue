<script setup>
/**
 * 管理员仪表板：系统概览 + 快捷入口。
 */
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { authStore } from "../../stores/auth.js";
import { api } from "../../api.js";

const router = useRouter();
const loading = ref(false);
const overview = ref({
  totalRequests: 0,
  activeTenants: 0,
  pendingReviews: 0,
  cacheHitRate: 0,
});

async function loadDashboard() {
  loading.value = true;
  try {
    const [costResp, tenantResp, reviewResp] = await Promise.allSettled([
      api.cost("model"),
      api.listTenants(),
      api.reviewQueue({ page_size: 1 }),
    ]);

    // 从 cost 数据提取总请求数和缓存命中率
    if (costResp.status === "fulfilled") {
      const data = costResp.value.data;
      const cache = data.semantic_cache || {};
      overview.value.cacheHitRate = cache.cached_entries > 0 ? (cache.threshold * 100).toFixed(1) : 0;
      const summary = data.runtime_summary || {};
      overview.value.totalRequests = summary.total_requests || 0;
    }

    // 从租户数据提取活跃租户数
    if (tenantResp.status === "fulfilled") {
      overview.value.activeTenants = (tenantResp.value.data.tenants || []).length;
    }

    // 待审核数
    if (reviewResp.status === "fulfilled") {
      overview.value.pendingReviews = reviewResp.value.data.total || 0;
    }
  } catch {} finally {
    loading.value = false;
  }
}

onMounted(loadDashboard);

const quickLinks = [
  { label: "能力矩阵", path: "/admin/capabilities", icon: "✅" },
  { label: "灰度管理", path: "/admin/rollout", icon: "🎯" },
  { label: "租户管理", path: "/admin/tenants", icon: "🏢" },
  { label: "成本面板", path: "/admin/cost", icon: "💰" },
  { label: "Trace 查看", path: "/admin/traces", icon: "🔬" },
  { label: "审核队列", path: "/risk/reviews", icon: "🔍" },
  { label: "对话控制台", path: "/chat", icon: "💬" },
];
</script>

<template>
  <div class="admin-dashboard">
    <header class="page-header">
      <h1>管理员仪表板</h1>
      <span class="welcome">{{ authStore.user?.display_name || '管理员' }} · {{ authStore.user?.tenant_id ? '租户 ' + authStore.tenantId : '' }}</span>
    </header>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon">📊</div>
        <div class="stat-num">{{ overview.totalRequests.toLocaleString() }}</div>
        <div class="stat-label">总请求数</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🏢</div>
        <div class="stat-num">{{ overview.activeTenants }}</div>
        <div class="stat-label">活跃租户</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">⏳</div>
        <div class="stat-num">{{ overview.pendingReviews }}</div>
        <div class="stat-label">待审核</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">⚡</div>
        <div class="stat-num">{{ overview.cacheHitRate }}%</div>
        <div class="stat-label">缓存命中率</div>
      </div>
    </div>

    <section class="section">
      <h2>快捷入口</h2>
      <div class="quick-links">
        <router-link
          v-for="link in quickLinks"
          :key="link.path"
          :to="link.path"
          class="quick-card"
        >
          <span class="ql-icon">{{ link.icon }}</span>
          <span class="ql-label">{{ link.label }}</span>
        </router-link>
      </div>
    </section>

    <section class="section" style="margin-top: 16px;">
      <h2>v1 / v2 / v3 版本对比</h2>
      <p class="section-desc">三版本功能差异化：v1 关键词基线 → v2 LLM 意图 + 规则风控 → v3 全 7-Agent 协作 + 三层融合风控</p>
      <div class="version-compare">
        <table class="version-table">
          <thead>
            <tr>
              <th>指标</th>
              <th class="v1">v1 基线</th>
              <th class="v2">v2 进阶</th>
              <th class="v3">v3 完整</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>意图识别</td>
              <td>关键词匹配</td>
              <td>LLM NLU</td>
              <td>LLM + 复杂度估计</td>
            </tr>
            <tr>
              <td>Agent 拓扑</td>
              <td>单 Agent</td>
              <td>单 Agent + 风控</td>
              <td>7 Agent 协作</td>
            </tr>
            <tr>
              <td>风控引擎</td>
              <td>无</td>
              <td>规则层</td>
              <td>规则 + 特征 + LLM 三层融合</td>
            </tr>
            <tr>
              <td>任务规划</td>
              <td>无</td>
              <td>无</td>
              <td>Planner + Critic</td>
            </tr>
            <tr>
              <td>人审 Interrupt</td>
              <td>无</td>
              <td>无</td>
              <td>支持</td>
            </tr>
            <tr>
              <td>Token 成本</td>
              <td>
                <div class="bar-track"><div class="bar bar-v1" style="width: 30%"></div></div>
                <span class="bar-label">低</span>
              </td>
              <td>
                <div class="bar-track"><div class="bar bar-v2" style="width: 60%"></div></div>
                <span class="bar-label">中</span>
              </td>
              <td>
                <div class="bar-track"><div class="bar bar-v3" style="width: 100%"></div></div>
                <span class="bar-label">高（精度优先）</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.admin-dashboard { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 22px; margin: 0; }
.welcome { color: #888; font-size: 14px; }
.stats-row { display: flex; gap: 16px; margin-bottom: 24px; }
.stat-card { flex: 1; padding: 20px; border-radius: 10px; text-align: center; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.stat-icon { font-size: 24px; margin-bottom: 6px; }
.stat-num { font-size: 26px; font-weight: 700; }
.stat-label { color: #888; font-size: 13px; margin-top: 4px; }
.section { background: #fff; border-radius: 10px; padding: 20px; }
.section h2 { font-size: 16px; margin: 0 0 16px; }
.quick-links { display: flex; gap: 12px; flex-wrap: wrap; }
.quick-card { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 20px 28px; border-radius: 10px; background: #f8f9fa; text-decoration: none; color: inherit; transition: all 0.15s; min-width: 100px; }
.quick-card:hover { background: #667eea; color: #fff; transform: translateY(-2px); }
.ql-icon { font-size: 28px; }
.ql-label { font-size: 13px; font-weight: 500; }
.section-desc { color: #667085; font-size: 13px; margin: -8px 0 16px; }
.version-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.version-table th, .version-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #eaecf0; }
.version-table th { background: #f9fafb; color: #667085; font-weight: 600; }
.version-table th.v1 { color: #667085; }
.version-table th.v2 { color: #175cd3; }
.version-table th.v3 { color: #7f56d9; }
.bar-track { width: 80px; height: 8px; background: #f2f4f7; border-radius: 4px; display: inline-block; vertical-align: middle; margin-right: 8px; }
.bar { height: 100%; border-radius: 4px; }
.bar-v1 { background: #98a2b3; }
.bar-v2 { background: #2e90fa; }
.bar-v3 { background: #7f56d9; }
.bar-label { font-size: 12px; color: #667085; vertical-align: middle; }
</style>
