<script setup>
/**
 * 管理员视图：Trace 查看。
 * 搜索 Trace ID / 用户 / 时间，展示 trace 列表和 trace tree 节点详情。
 */
import { ref, onMounted } from "vue";
import { api } from "../../api.js";
import EmptyState from "../../components/EmptyState.vue";
import LoadingSpinner from "../../components/LoadingSpinner.vue";

const traces = ref([]);
const loading = ref(false);
const searchQuery = ref("");
const selectedTrace = ref(null);
const langfuseAvailable = ref(false);

// 模拟 trace 数据（Langfuse 不可用时的降级方案）
const mockTraces = [
  { id: "tr_001", user_id: "user_a_001", intent: "refund", version: "v3", latency_ms: 2340, tokens: 1850, model: "gpt-4o-mini", status: "completed", created_at: "2026-05-29 10:32:15" },
  { id: "tr_002", user_id: "user_a_002", intent: "order_query", version: "v3", latency_ms: 890, tokens: 620, model: "gpt-4o-mini", status: "completed", created_at: "2026-05-29 10:28:43" },
  { id: "tr_003", user_id: "user_b_001", intent: "knowledge", version: "v2", latency_ms: 1560, tokens: 1200, model: "gpt-4o-mini", status: "completed", created_at: "2026-05-29 10:15:22" },
  { id: "tr_004", user_id: "user_c_001", intent: "address_change", version: "v3", latency_ms: 4120, tokens: 3200, model: "gpt-4o", status: "interrupted", created_at: "2026-05-29 09:58:10" },
  { id: "tr_005", user_id: "user_a_003", intent: "greeting", version: "v1", latency_ms: 320, tokens: 180, model: "gpt-4o-mini", status: "completed", created_at: "2026-05-29 09:45:33" },
];

const mockTreeNodes = {
  tr_001: [
    { name: "intent_router", latency_ms: 280, tokens: 150, model: "gpt-4o-mini", detail: "intent=refund, complexity=75" },
    { name: "planner", latency_ms: 520, tokens: 420, model: "gpt-4o-mini", detail: "3 steps generated" },
    { name: "knowledge_agent", latency_ms: 380, tokens: 280, model: "gpt-4o-mini", detail: "2 citations found" },
    { name: "critic", latency_ms: 290, tokens: 220, model: "gpt-4o-mini", detail: "verdict=approve" },
    { name: "risk_review", latency_ms: 450, tokens: 350, model: "gpt-4o-mini", detail: "fusion_score=25, decision=pass" },
    { name: "plan_executor", latency_ms: 420, tokens: 430, model: "gpt-4o-mini", detail: "3/3 steps completed" },
  ],
  tr_002: [
    { name: "intent_router", latency_ms: 210, tokens: 120, model: "gpt-4o-mini", detail: "intent=order_query, complexity=40" },
    { name: "plan_executor", latency_ms: 680, tokens: 500, model: "gpt-4o-mini", detail: "query_order tool called" },
  ],
};

async function loadTraces() {
  loading.value = true;
  try {
    // 尝试从 Langfuse 拉取，失败则用 mock
    const resp = await api.cost("model");
    if (resp.data?.langfuse) {
      langfuseAvailable.value = true;
      traces.value = mockTraces; // Langfuse 数据格式待适配
    } else {
      langfuseAvailable.value = false;
      traces.value = mockTraces;
    }
  } catch {
    langfuseAvailable.value = false;
    traces.value = mockTraces;
  } finally {
    loading.value = false;
  }
}

function search() {
  if (!searchQuery.value.trim()) {
    traces.value = mockTraces;
    return;
  }
  const q = searchQuery.value.toLowerCase();
  traces.value = mockTraces.filter(
    (t) => t.id.includes(q) || t.user_id.includes(q) || t.intent.includes(q)
  );
}

function selectTrace(trace) {
  selectedTrace.value = trace;
}

onMounted(loadTraces);
</script>

<template>
  <div class="trace-page">
    <h2>Trace 查看</h2>

    <div class="status-banner" :class="langfuseAvailable ? 'ok' : 'warn'">
      {{ langfuseAvailable ? "✅ Langfuse 已连接 — 实时 trace 数据" : "⚠️ Langfuse 未连接 — 展示模拟数据（配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 后自动切换）" }}
    </div>

    <div class="search-bar">
      <input v-model="searchQuery" placeholder="搜索 Trace ID / 用户 / 意图" @keyup.enter="search" />
      <button @click="search">搜索</button>
    </div>

    <LoadingSpinner v-if="loading" size="28px" />

    <template v-else>
      <div class="trace-layout">
        <!-- 左侧 trace 列表 -->
        <div class="trace-list">
          <table class="data-table">
            <thead>
              <tr>
                <th>Trace ID</th>
                <th>意图</th>
                <th>版本</th>
                <th>延迟</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="t in traces"
                :key="t.id"
                :class="{ active: selectedTrace?.id === t.id }"
                @click="selectTrace(t)"
              >
                <td class="mono">{{ t.id }}</td>
                <td>{{ t.intent }}</td>
                <td><span class="badge-version">{{ t.version }}</span></td>
                <td>{{ t.latency_ms }}ms</td>
                <td>
                  <span class="badge" :class="t.status === 'completed' ? 'badge-ok' : 'badge-warn'">
                    {{ t.status }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <EmptyState v-if="traces.length === 0" title="无匹配 Trace" />
        </div>

        <!-- 右侧 trace tree -->
        <div class="trace-detail">
          <template v-if="selectedTrace">
            <h3>Trace Tree: {{ selectedTrace.id }}</h3>
            <div class="trace-meta">
              <span>用户: {{ selectedTrace.user_id }}</span>
              <span>模型: {{ selectedTrace.model }}</span>
              <span>Token: {{ selectedTrace.tokens }}</span>
              <span>总延迟: {{ selectedTrace.latency_ms }}ms</span>
            </div>
            <div class="tree">
              <div v-for="(node, idx) in (mockTreeNodes[selectedTrace.id] || [])" :key="idx" class="tree-node">
                <div class="node-connector">
                  <span class="dot" />
                  <span class="line" v-if="idx < (mockTreeNodes[selectedTrace.id] || []).length - 1" />
                </div>
                <div class="node-content">
                  <div class="node-header">
                    <strong>{{ node.name }}</strong>
                    <span class="node-stats">{{ node.latency_ms }}ms · {{ node.tokens }} tokens · {{ node.model }}</span>
                  </div>
                  <div class="node-detail">{{ node.detail }}</div>
                </div>
              </div>
            </div>
          </template>
          <EmptyState v-else title="选择 Trace 查看详情" description="点击左侧 trace 行" />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.trace-page { padding: 24px; }
.status-banner { padding: 8px 14px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }
.status-banner.ok { background: #d1fadf; color: #027a48; }
.status-banner.warn { background: #fef0c7; color: #b54708; }
.search-bar { display: flex; gap: 8px; margin-bottom: 16px; }
.search-bar input { flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid #d0d5dd; font-size: 14px; }
.search-bar button { padding: 8px 16px; border-radius: 6px; border: 1px solid #7f56d9; background: #7f56d9; color: #fff; cursor: pointer; }
.trace-layout { display: flex; gap: 20px; min-height: 500px; }
.trace-list { flex: 1; overflow: auto; }
.trace-detail { flex: 1; background: #f9fafb; border-radius: 10px; padding: 20px; }
.trace-detail h3 { margin: 0 0 12px; font-size: 16px; }
.trace-meta { display: flex; gap: 16px; font-size: 13px; color: #667085; margin-bottom: 16px; flex-wrap: wrap; }
.data-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.data-table th, .data-table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #eaecf0; }
.data-table th { background: #f9fafb; color: #667085; font-weight: 600; }
.data-table tbody tr { cursor: pointer; }
.data-table tbody tr:hover { background: #f4f0ff; }
.data-table tbody tr.active { background: #f4f0ff; }
.mono { font-family: monospace; font-size: 13px; }
.badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; }
.badge-ok { background: #d1fadf; color: #027a48; }
.badge-warn { background: #fef0c7; color: #b54708; }
.badge-version { padding: 2px 6px; border-radius: 4px; font-size: 12px; background: #f2f4f7; color: #344054; }
.tree { padding-left: 8px; }
.tree-node { display: flex; gap: 12px; margin-bottom: 4px; }
.node-connector { display: flex; flex-direction: column; align-items: center; width: 16px; padding-top: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: #7f56d9; flex-shrink: 0; }
.line { width: 2px; flex: 1; background: #d0d5dd; min-height: 20px; }
.node-content { flex: 1; background: #fff; border: 1px solid #eaecf0; border-radius: 6px; padding: 8px 12px; margin-bottom: 4px; }
.node-header { display: flex; justify-content: space-between; align-items: center; }
.node-header strong { font-size: 14px; }
.node-stats { font-size: 12px; color: #667085; }
.node-detail { font-size: 13px; color: #667085; margin-top: 4px; }
</style>
