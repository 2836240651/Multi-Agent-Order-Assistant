<script setup>
/**
 * 能力矩陣面板：對照「代碼存在 / 可演示」兩列，一鍵探測後端子系統。
 */
import { ref, onMounted } from "vue";
import { api } from "../../api.js";

const loading = ref(false);
const caps = ref({});
const summary = ref({ total: 0, demo_ready: 0 });
const probedAt = ref("");

const LABELS = {
  rag: "RAG 混合檢索",
  agents: "7-Agent / LangGraph",
  eval: "Eval 體系",
  langfuse: "Langfuse trace",
  risk: "三層風控",
  llm_cache: "模型路由 + 語義緩存",
  celery: "Celery 異步",
  rollout: "灰度 v1/v2/v3",
  auth: "JWT + RBAC + 多租戶",
  mcp: "MCP stdio",
  frontend: "四角色前端",
};

const DEMO_HINTS = {
  rag: "/chat — 問「無理由退貨幾天」應有引用",
  agents: "/chat — 高額退款觸發 v3 圖 + interrupt",
  eval: "make eval-smoke",
  langfuse: "/admin/traces",
  risk: "/risk/reviews — 高額退款人審",
  llm_cache: "/admin/cost — 語義緩存條目",
  celery: "客服台批量審核任務",
  rollout: "/admin/rollout — A/B 權重",
  auth: "四角色登入切換",
  mcp: "docs/mcp_integration.md + Claude Desktop",
  frontend: "/agent/conversation/:threadId",
};

async function probe() {
  loading.value = true;
  try {
    const { data } = await api.capabilities();
    const { summary: s, ...rest } = data;
    caps.value = rest;
    summary.value = s || { total: Object.keys(rest).length, demo_ready: 0 };
    probedAt.value = new Date().toLocaleString();
  } catch (e) {
    caps.value = {};
    summary.value = { total: 0, demo_ready: 0 };
  } finally {
    loading.value = false;
  }
}

onMounted(probe);

function rows() {
  return Object.entries(caps.value)
    .filter(([k]) => k !== "summary")
    .map(([key, val]) => ({
      key,
      label: LABELS[key] || key,
      hint: DEMO_HINTS[key] || "",
      ...(typeof val === "object" ? val : {}),
    }));
}
</script>

<template>
  <div class="cap-page">
    <header class="page-header">
      <div>
        <h1>能力矩陣</h1>
        <p class="sub">代碼存在 vs 可演示 — 一鍵探測後端子系統</p>
      </div>
      <el-button type="primary" :loading="loading" @click="probe">重新探測</el-button>
    </header>

    <div v-if="probedAt" class="summary-bar">
      <span>探測時間：{{ probedAt }}</span>
      <span class="pill ok">{{ summary.demo_ready }} / {{ summary.total }} 可演示</span>
    </div>

    <el-table v-loading="loading" :data="rows()" stripe class="cap-table">
      <el-table-column label="能力" prop="label" min-width="180" />
      <el-table-column label="代碼存在" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="row.code_exists ? 'success' : 'info'" size="small">
            {{ row.code_exists ? "是" : "否" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="可演示" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="row.demo_ready ? 'success' : 'warning'" size="small">
            {{ row.demo_ready ? "是" : "否" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="探測詳情" prop="detail" min-width="220" show-overflow-tooltip />
      <el-table-column label="演示路徑" min-width="200">
        <template #default="{ row }">
          <code class="hint">{{ row.hint }}</code>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.cap-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-header h1 {
  margin: 0 0 4px;
  font-size: 1.5rem;
}
.sub {
  margin: 0;
  color: #64748b;
  font-size: 0.9rem;
}
.summary-bar {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 0.85rem;
  color: #475569;
}
.pill.ok {
  background: #dcfce7;
  color: #166534;
  padding: 4px 12px;
  border-radius: 999px;
  font-weight: 600;
}
.hint {
  font-size: 0.75rem;
  color: #334155;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
