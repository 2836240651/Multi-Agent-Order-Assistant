<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api";
import { useToast } from "../composables/useToast";
import ChartPanel from "../components/ChartPanel.vue";
import LoadingSpinner from "../components/LoadingSpinner.vue";
import EmptyState from "../components/EmptyState.vue";

const toast = useToast();

const dashboard = ref(null);
const loading = reactive({ dashboard: true, rollout: false });

const rolloutForm = reactive({
  baseline_v1: 10,
  optimized_v2: 20,
  current_v3: 70,
});

const runtimeSummary = computed(() => dashboard.value?.runtime || dashboard.value?.runtime_observability || {});
const rolloutSummary = computed(() => dashboard.value?.rollout || {});
const recentEvents = computed(() => runtimeSummary.value.recent_events || []);

const totalWeight = computed(() => {
  return rolloutForm.baseline_v1 + rolloutForm.optimized_v2 + rolloutForm.current_v3;
});

async function loadDashboard() {
  loading.dashboard = true;
  try {
    dashboard.value = await api.opsOverview();
    const weights = rolloutSummary.value.weights || {};
    rolloutForm.baseline_v1 = weights.baseline_v1 ?? rolloutForm.baseline_v1;
    rolloutForm.optimized_v2 = weights.optimized_v2 ?? rolloutForm.optimized_v2;
    rolloutForm.current_v3 = weights.current_v3 ?? rolloutForm.current_v3;
  } catch (error) {
    toast.error(`加载失败: ${error.message}`);
  } finally {
    loading.dashboard = false;
  }
}

async function updateRollout() {
  if (totalWeight.value !== 100) {
    toast.warning(`权重总和必须是 100%，当前总和: ${totalWeight.value}%`);
    return;
  }
  loading.rollout = true;
  try {
    await api.updateRollout({
      baseline_v1: Number(rolloutForm.baseline_v1),
      optimized_v2: Number(rolloutForm.optimized_v2),
      current_v3: Number(rolloutForm.current_v3),
    });
    toast.success("灰度配置已更新");
    await loadDashboard();
  } catch (error) {
    toast.error(`更新失败: ${error.message}`);
  } finally {
    loading.rollout = false;
  }
}

const rolloutChartOption = computed(() => {
  return {
    tooltip: {
      trigger: "item",
      formatter: "{b}: {d}%",
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
        radius: ["45%", "70%"],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: "#fff",
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: "{b}\n{d}%",
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: "bold",
          },
        },
        data: [
          { name: "baseline_v1", value: rolloutForm.baseline_v1 },
          { name: "optimized_v2", value: rolloutForm.optimized_v2 },
          { name: "current_v3", value: rolloutForm.current_v3 },
        ],
      },
    ],
  };
});

const latencyBarOption = computed(() => {
  const byVariant = runtimeSummary.value.by_variant || {};
  const variants = ["baseline_v1", "optimized_v2", "current_v3"];
  const avgLatencies = variants.map((v) => byVariant[v]?.avg_latency_ms || 0);
  const requests = variants.map((v) => byVariant[v]?.requests || 0);

  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
    },
    legend: {
      data: ["平均延迟", "请求数"],
      top: 0,
    },
    grid: {
      left: 50,
      right: 20,
      top: 50,
      bottom: 30,
    },
    xAxis: {
      type: "category",
      data: variants,
      axisLine: { lineStyle: { color: "#e8ecf0" } },
      axisLabel: { color: "#627983" },
    },
    yAxis: [
      {
        type: "value",
        name: "延迟(ms)",
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#f0f4f8" } },
        axisLabel: { color: "#627983" },
      },
      {
        type: "value",
        name: "请求数",
        axisLine: { show: false },
        splitLine: { show: false },
        axisLabel: { color: "#627983" },
      },
    ],
    series: [
      {
        name: "平均延迟",
        type: "bar",
        barWidth: "40%",
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "#d95f3c" },
              { offset: 1, color: "#f09762" },
            ],
          },
          borderRadius: [4, 4, 0, 0],
        },
        data: avgLatencies,
      },
      {
        name: "请求数",
        type: "line",
        yAxisIndex: 1,
        symbol: "circle",
        symbolSize: 8,
        lineStyle: { color: "#305164", width: 2 },
        itemStyle: { color: "#305164" },
        data: requests,
      },
    ],
  };
});

onMounted(loadDashboard);
</script>

<template>
  <div class="ops-view">
    <header class="view-header">
      <div>
        <h1>运维控制台</h1>
        <p>运行时观测、灰度配置、成本估算</p>
      </div>
      <button class="ghost-button" @click="loadDashboard" :disabled="loading.dashboard">
        <LoadingSpinner v-if="loading.dashboard" size="14px" />
        <span v-if="loading.dashboard">加载中...</span>
        <span v-else>🔄 刷新</span>
      </button>
    </header>

    <div class="ops-content">
      <div class="ops-grid">
        <section class="panel">
          <div class="panel-head">
            <h2>📊 运行指标</h2>
          </div>
          <div class="metrics-grid">
            <div class="metric-item">
              <span class="metric-value">{{ runtimeSummary.requests ?? 0 }}</span>
              <span class="metric-label">总请求数</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ runtimeSummary.avg_latency_ms ?? 0 }} ms</span>
              <span class="metric-label">平均延迟</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ runtimeSummary.manual_review_rate ?? 0 }}</span>
              <span class="metric-label">人工接管率</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ runtimeSummary.degraded_rate ?? 0 }}</span>
              <span class="metric-label">降级率</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">{{ runtimeSummary.error_rate ?? 0 }}</span>
              <span class="metric-label">错误率</span>
            </div>
            <div class="metric-item">
              <span class="metric-value">${{ runtimeSummary.estimated_total_cost_usd ?? 0 }}</span>
              <span class="metric-label">预估成本</span>
            </div>
          </div>

          <div class="chart-section">
            <h3>版本延迟与请求对比</h3>
            <ChartPanel :option="latencyBarOption" height="250px" />
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>🎛️ 灰度配置</h2>
          </div>

          <div class="rollout-chart">
            <ChartPanel :option="rolloutChartOption" height="220px" />
          </div>

          <div class="rollout-form">
            <div class="rollout-sliders">
              <div class="slider-item">
                <div class="slider-header">
                  <span class="slider-label">
                    <span class="variant-dot v1"></span>
                    baseline_v1
                  </span>
                  <span class="slider-value">{{ rolloutForm.baseline_v1 }}%</span>
                </div>
                <input
                  v-model.number="rolloutForm.baseline_v1"
                  type="range"
                  min="0"
                  max="100"
                  class="slider"
                />
              </div>
              <div class="slider-item">
                <div class="slider-header">
                  <span class="slider-label">
                    <span class="variant-dot v2"></span>
                    optimized_v2
                  </span>
                  <span class="slider-value">{{ rolloutForm.optimized_v2 }}%</span>
                </div>
                <input
                  v-model.number="rolloutForm.optimized_v2"
                  type="range"
                  min="0"
                  max="100"
                  class="slider"
                />
              </div>
              <div class="slider-item">
                <div class="slider-header">
                  <span class="slider-label">
                    <span class="variant-dot v3"></span>
                    current_v3
                  </span>
                  <span class="slider-value">{{ rolloutForm.current_v3 }}%</span>
                </div>
                <input
                  v-model.number="rolloutForm.current_v3"
                  type="range"
                  min="0"
                  max="100"
                  class="slider"
                />
              </div>
            </div>

            <div class="weight-total" :class="{ error: totalWeight !== 100 }">
              权重总和: {{ totalWeight }}% {{ totalWeight !== 100 ? "(必须等于 100%)" : "✓" }}
            </div>

            <button
              class="primary-button full-width"
              :disabled="loading.rollout || totalWeight !== 100"
              @click="updateRollout"
            >
              <LoadingSpinner v-if="loading.rollout" size="16px" color="#fff" />
              <span v-if="loading.rollout">更新中...</span>
              <span v-else>💾 保存灰度配置</span>
            </button>
          </div>
        </section>
      </div>

      <section class="panel panel-full">
        <div class="panel-head">
          <h2>📈 最近运行事件</h2>
        </div>
        <div v-if="recentEvents.length" class="table-wrap">
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
              <tr v-for="(event, idx) in recentEvents" :key="idx">
                <td class="cell-time">{{ event.timestamp?.split("T")[1]?.slice(0, 8) || "-" }}</td>
                <td>
                  <span class="variant-tag" :class="event.variant?.replace('_', '-')">
                    {{ event.variant }}
                  </span>
                </td>
                <td>{{ event.action || "-" }}</td>
                <td>
                  <span class="status-text" :class="'status-' + event.status">
                    {{ event.status }}
                  </span>
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
        <EmptyState v-else icon="📈" title="暂无运行事件" description="发送请求后这里会显示运行事件" />
      </section>
    </div>
  </div>
</template>
