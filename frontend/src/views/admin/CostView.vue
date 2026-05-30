<script setup>
/**
 * 管理员视图：成本面板（token 用量 / 缓存命中 / 按模型分组）。
 */
import { ref, onMounted } from "vue";
import { api } from "../../api.js";

const groupBy = ref("model");
const data = ref(null);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    const resp = await api.cost(groupBy.value);
    data.value = resp.data;
  } catch (e) {
    data.value = { error: e.message };
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="cost-view">
    <header class="page-header">
      <h1>成本面板</h1>
      <div class="group-tabs">
        <button
          v-for="g in ['model', 'agent', 'version', 'tenant']"
          :key="g"
          :class="{ active: groupBy === g }"
          @click="groupBy = g; load()"
        >{{ g }}</button>
      </div>
    </header>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-if="data && !loading" class="cost-content">
      <!-- Runtime Summary -->
      <div class="summary-cards" v-if="data.runtime_summary">
        <div class="s-card">
          <div class="s-num">{{ data.runtime_summary.requests || 0 }}</div>
          <div class="s-label">总请求数</div>
        </div>
        <div class="s-card">
          <div class="s-num">{{ ((data.runtime_summary.error_rate || 0) * 100).toFixed(1) }}%</div>
          <div class="s-label">错误率</div>
        </div>
        <div class="s-card">
          <div class="s-num">{{ (data.runtime_summary.avg_latency_ms || 0).toFixed(0) }}ms</div>
          <div class="s-label">平均延迟</div>
        </div>
        <div class="s-card">
          <div class="s-num">{{ (data.runtime_summary.estimated_total_tokens || 0).toLocaleString() }}</div>
          <div class="s-label">总 Token</div>
        </div>
      </div>

      <!-- Semantic Cache -->
      <div class="cache-section" v-if="data.semantic_cache">
        <h2>语义缓存</h2>
        <div class="cache-stats">
          <span>缓存条目: <strong>{{ data.semantic_cache.cached_entries }}</strong></span>
          <span>阈值: <strong>{{ data.semantic_cache.threshold }}</strong></span>
          <span>TTL: <strong>{{ data.semantic_cache.ttl_seconds }}s</strong></span>
        </div>
      </div>

      <!-- Version breakdown -->
      <div class="version-table" v-if="data.runtime_summary?.by_variant">
        <h2>按版本分组</h2>
        <table>
          <thead>
            <tr><th>版本</th><th>请求数</th><th>错误率</th><th>平均延迟</th><th>Token</th><th>成本($)</th></tr>
          </thead>
          <tbody>
            <tr v-for="(stats, ver) in data.runtime_summary.by_variant" :key="ver">
              <td>{{ ver }}</td>
              <td>{{ stats.requests }}</td>
              <td>{{ (stats.error_rate * 100).toFixed(1) }}%</td>
              <td>{{ stats.avg_latency_ms.toFixed(0) }}ms</td>
              <td>{{ stats.estimated_tokens.toLocaleString() }}</td>
              <td>${{ stats.estimated_cost_usd.toFixed(4) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Empty state -->
      <div v-if="!data.runtime_summary?.requests" class="empty-note">
        暂无运行时数据。发起请求后此处将展示 Token 用量和成本统计。
        <br/>连接 Langfuse 后可获得完整模型级成本分析。
      </div>
    </div>
  </div>
</template>

<style scoped>
.cost-view { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 22px; margin: 0; }
.group-tabs { display: flex; gap: 4px; }
.group-tabs button { padding: 6px 14px; border: 1px solid #ddd; background: #fff; border-radius: 6px; cursor: pointer; font-size: 13px; }
.group-tabs button.active { background: #667eea; color: #fff; border-color: #667eea; }
.loading { text-align: center; color: #888; padding: 40px; }
.summary-cards { display: flex; gap: 16px; margin-bottom: 24px; }
.s-card { flex: 1; padding: 20px; background: #fff; border-radius: 10px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.s-num { font-size: 24px; font-weight: 700; }
.s-label { color: #888; font-size: 13px; margin-top: 4px; }
.cache-section, .version-table { background: #fff; border-radius: 10px; padding: 20px; margin-bottom: 16px; }
.cache-section h2, .version-table h2 { font-size: 16px; margin: 0 0 12px; }
.cache-stats { display: flex; gap: 20px; font-size: 14px; }
.version-table table { width: 100%; border-collapse: collapse; font-size: 13px; }
.version-table th, .version-table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
.empty-note { text-align: center; color: #999; padding: 40px; line-height: 2; }
</style>
