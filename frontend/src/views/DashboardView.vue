<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { useToast } from "../composables/useToast";
import ChartPanel from "../components/ChartPanel.vue";
import QuickActions from "../components/QuickActions.vue";
import LoadingSpinner from "../components/LoadingSpinner.vue";
import EmptyState from "../components/EmptyState.vue";

const router = useRouter();
const toast = useToast();

const dashboard = ref(null);
const reviews = ref([]);
const systemHealth = ref(null);
const loading = reactive({ dashboard: true });

const runtimeSummary = computed(() => dashboard.value?.runtime || dashboard.value?.runtime_observability || {});
const recentEvents = computed(() => runtimeSummary.value.recent_events || []);
const pendingReviewsCount = computed(() => reviews.value.length);

const quickActions = [
  { key: "chat", label: "发起对话", icon: "💬", path: "/chat" },
  { key: "reviews", label: "处理复核", icon: "🔍", path: "/reviews" },
  { key: "audit", label: "查看审计", icon: "📋", path: "/audit" },
  { key: "ops", label: "运维配置", icon: "⚙️", path: "/ops" },
];

async function loadDashboard() {
  loading.dashboard = true;
  try {
    const [health, overview, reviewResp] = await Promise.all([
      api.health(),
      api.opsOverview(),
      api.pendingReviews(),
    ]);
    systemHealth.value = health;
    dashboard.value = overview;
    reviews.value = reviewResp.items || [];
  } catch (error) {
    toast.error(`加载失败: ${error.message}`);
  } finally {
    loading.dashboard = false;
  }
}

function handleQuickAction(item) {
  router.push(item.path);
}

const pieChartOption = computed(() => {
  const byVariant = runtimeSummary.value.by_variant || {};
  const data = Object.entries(byVariant).map(([name, stats]) => ({
    name: name,
    value: stats.requests || 0,
  }));
  return {
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} ({d}%)",
    },
    legend: {
      orient: "vertical",
      right: 10,
      top: "center",
    },
    color: ["#627983", "#f09762", "#d95f3c"],
    series: [
      {
        type: "pie",
        radius: ["50%", "75%"],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 6,
          borderColor: "#fff",
          borderWidth: 2,
        },
        label: {
          show: false,
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: "bold",
          },
        },
        data: data.length > 0 ? data : [{ name: "暂无数据", value: 0 }],
      },
    ],
  };
});

const latencyChartOption = computed(() => {
  const events = recentEvents.value.slice(0, 10).reverse();
  const times = events.map((e) => e.timestamp?.split("T")[1]?.slice(0, 5) || "");
  const latencies = events.map((e) => e.latency_ms || 0);
  return {
    tooltip: {
      trigger: "axis",
    },
    grid: {
      left: 50,
      right: 20,
      top: 30,
      bottom: 30,
    },
    xAxis: {
      type: "category",
      data: times,
      axisLine: { lineStyle: { color: "#e8ecf0" } },
      axisLabel: { color: "#627983", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      splitLine: { lineStyle: { color: "#f0f4f8" } },
      axisLabel: { color: "#627983", fontSize: 11 },
    },
    series: [
      {
        name: "延迟",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { color: "#d95f3c", width: 2 },
        itemStyle: { color: "#d95f3c" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(217, 95, 60, 0.3)" },
              { offset: 1, color: "rgba(217, 95, 60, 0)" },
            ],
          },
        },
        data: latencies,
      },
    ],
  };
});

onMounted(loadDashboard);
</script>

<template>
  <div class="dashboard">
    <header class="view-header">
      <div>
        <h1>系统概览</h1>
        <p>RetailGuard Copilot 多智能体客服控制台</p>
      </div>
      <div class="header-actions">
        <button class="ghost-button" @click="loadDashboard" :disabled="loading.dashboard">
          <span v-if="loading.dashboard"><LoadingSpinner size="16px" /> 加载中...</span>
          <span v-else>🔄 刷新</span>
        </button>
        <div class="health-badges">
          <div class="badge-card" :class="{ healthy: systemHealth?.status === 'healthy' }">
            <span>服务状态</span>
            <strong>{{ systemHealth?.status === "healthy" ? "🟢 正常" : "🔴 异常" }}</strong>
          </div>
          <div class="badge-card">
            <span>版本</span>
            <strong>{{ systemHealth?.version || "-" }}</strong>
          </div>
        </div>
      </div>
    </header>

    <div class="dashboard-content">
      <section class="quick-section">
        <h3 class="section-title">快捷操作</h3>
        <QuickActions :items="quickActions" @click="handleQuickAction" />
      </section>

      <div class="stats-grid">
        <article class="stat-card">
          <div class="stat-icon requests">📊</div>
          <div class="stat-content">
            <span class="stat-label">总请求数</span>
            <strong class="stat-value">{{ runtimeSummary.requests ?? 0 }}</strong>
          </div>
        </article>
        <article class="stat-card">
          <div class="stat-icon latency">⚡</div>
          <div class="stat-content">
            <span class="stat-label">平均延迟</span>
            <strong class="stat-value">{{ runtimeSummary.avg_latency_ms ?? 0 }} ms</strong>
          </div>
        </article>
        <article class="stat-card">
          <div class="stat-icon review">🔍</div>
          <div class="stat-content">
            <span class="stat-label">待人工复核</span>
            <strong class="stat-value">{{ pendingReviewsCount }}</strong>
          </div>
        </article>
        <article class="stat-card">
          <div class="stat-icon degraded">⚠️</div>
          <div class="stat-content">
            <span class="stat-label">降级率</span>
            <strong class="stat-value">{{ runtimeSummary.degraded_rate ?? 0 }}</strong>
          </div>
        </article>
        <article class="stat-card">
          <div class="stat-icon error-rate">❌</div>
          <div class="stat-content">
            <span class="stat-label">错误率</span>
            <strong class="stat-value">{{ runtimeSummary.error_rate ?? 0 }}</strong>
          </div>
        </article>
        <article class="stat-card">
          <div class="stat-icon cost">💰</div>
          <div class="stat-content">
            <span class="stat-label">预估成本</span>
            <strong class="stat-value">${{ runtimeSummary.estimated_total_cost_usd ?? 0 }}</strong>
          </div>
        </article>
      </div>

      <div class="dashboard-grid">
        <section class="panel">
          <div class="panel-head">
            <h2>版本请求分布</h2>
          </div>
          <ChartPanel :option="pieChartOption" height="280px" />
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>延迟趋势 (最近10条)</h2>
          </div>
          <ChartPanel :option="latencyChartOption" height="280px" />
        </section>
      </div>

      <section class="panel panel-full">
        <div class="panel-head">
          <h2>最新运行事件</h2>
        </div>
        <div v-if="recentEvents.length" class="event-table">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>版本</th>
                <th>动作</th>
                <th>状态</th>
                <th>延迟</th>
                <th>人工复核</th>
                <th>降级</th>
                <th>成本</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(event, idx) in recentEvents.slice(0, 10)" :key="idx">
                <td class="cell-time">{{ event.timestamp?.split("T")[1]?.slice(0, 8) || "-" }}</td>
                <td>
                  <span class="variant-tag" :class="event.variant?.replace('_', '-')">
                    {{ event.variant }}
                  </span>
                </td>
                <td>{{ event.action || "-" }}</td>
                <td>
                  <span :class="'status-' + event.status">{{ event.status }}</span>
                </td>
                <td class="cell-num">{{ event.latency_ms }} ms</td>
                <td>
                  <span :class="event.manual_review ? 'bool-yes' : 'bool-no'">
                    {{ event.manual_review ? "是" : "否" }}
                  </span>
                </td>
                <td>
                  <span :class="event.degraded ? 'bool-yes' : 'bool-no'">
                    {{ event.degraded ? "是" : "否" }}
                  </span>
                </td>
                <td class="cell-num">${{ event.estimated_cost_usd }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState v-else icon="📭" title="暂无运行事件" description="发送请求后这里会显示运行事件" />
      </section>
    </div>
  </div>
</template>
