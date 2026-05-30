<script setup>
/**
 * 风控视图：风险决策链可视化。
 * 三层决策树（规则/特征/LLM）+ 加权融合分数 + 操作按钮。
 */
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../../api.js";
import LoadingSpinner from "../../components/LoadingSpinner.vue";

const route = useRoute();
const router = useRouter();

const refund = ref(null);
const loading = ref(true);
const note = ref("");
const acting = ref(false);

const expanded = ref({ rules: true, features: false, llm: false });

async function load() {
  loading.value = true;
  try {
    const resp = await api.getRefund(route.params.refundNo);
    refund.value = resp.data;
  } catch {
    refund.value = null;
  } finally {
    loading.value = false;
  }
}

function toggle(layer) {
  expanded.value[layer] = !expanded.value[layer];
}

async function reviewAction(action) {
  if (["reject", "escalate"].includes(action) && !note.value.trim()) {
    alert("请填写审核备注");
    return;
  }
  acting.value = true;
  try {
    await api.reviewRefund(refund.value.refund_no, action, note.value);
    await load();
    note.value = "";
  } catch (e) {
    alert(e.response?.data?.message || "操作失败");
  } finally {
    acting.value = false;
  }
}

function scoreColor(score) {
  if (score >= 80) return "#d92d20";
  if (score >= 60) return "#f79009";
  return "#027a48";
}

onMounted(load);
</script>

<template>
  <div class="risk-decision-page">
    <button class="btn-back" @click="router.back()">← 返回</button>

    <LoadingSpinner v-if="loading" size="32px" />
    <div v-else-if="!refund" class="error">退款记录不存在</div>

    <template v-else>
      <h2>风险决策链</h2>

      <!-- 头部概览 -->
      <div class="header-card">
        <div class="header-row">
          <div><span class="label">退款编号</span><strong>{{ refund.refund_no }}</strong></div>
          <div><span class="label">金额</span><strong>¥{{ (refund.amount || 0).toFixed(2) }}</strong></div>
          <div>
            <span class="label">风险评分</span>
            <span class="score" :style="{ color: scoreColor(refund.risk_score || 0) }">
              {{ refund.risk_score ?? "—" }}
            </span>
          </div>
          <div><span class="label">状态</span><span class="status">{{ refund.status }}</span></div>
        </div>
      </div>

      <!-- 三层决策树 -->
      <div class="decision-tree">
        <!-- 规则层 -->
        <div class="layer" :class="{ expanded: expanded.rules }">
          <div class="layer-header" @click="toggle('rules')">
            <span class="layer-icon">📋</span>
            <span class="layer-title">规则层</span>
            <span class="layer-score" v-if="refund.risk_decision">命中规则</span>
            <span class="expand-icon">{{ expanded.rules ? "▼" : "▶" }}</span>
          </div>
          <div class="layer-body" v-if="expanded.rules">
            <div class="evidence-card">
              <p v-if="refund.risk_decision">风控决策: <code>{{ refund.risk_decision }}</code></p>
              <p v-else>未触发规则</p>
            </div>
          </div>
        </div>

        <!-- 特征层 -->
        <div class="layer" :class="{ expanded: expanded.features }">
          <div class="layer-header" @click="toggle('features')">
            <span class="layer-icon">📊</span>
            <span class="layer-title">特征层</span>
            <span class="expand-icon">{{ expanded.features ? "▼" : "▶" }}</span>
          </div>
          <div class="layer-body" v-if="expanded.features">
            <div class="evidence-card">
              <p>风险评分: <strong>{{ refund.risk_score ?? "—" }}</strong></p>
              <p>退款原因: {{ refund.reason }}</p>
            </div>
          </div>
        </div>

        <!-- LLM 层 -->
        <div class="layer" :class="{ expanded: expanded.llm }">
          <div class="layer-header" @click="toggle('llm')">
            <span class="layer-icon">🤖</span>
            <span class="layer-title">LLM 语义评估层</span>
            <span class="expand-icon">{{ expanded.llm ? "▼" : "▶" }}</span>
          </div>
          <div class="layer-body" v-if="expanded.llm">
            <div class="evidence-card">
              <p>{{ refund.description || "无详细描述" }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 操作 -->
      <div class="action-panel" v-if="!['done','denied','resolved','rejected'].includes(refund.status)">
        <h3>审核操作</h3>
        <textarea v-model="note" placeholder="审核备注" rows="3" />
        <div class="btn-group">
          <button class="btn btn-ok" :disabled="acting" @click="reviewAction('approve')">批准</button>
          <button class="btn btn-err" :disabled="acting" @click="reviewAction('reject')">拒绝</button>
          <button class="btn btn-warn" :disabled="acting" @click="reviewAction('escalate')">升级管理员</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.risk-decision-page { padding: 24px; max-width: 800px; margin: 0 auto; }
.btn-back { background: none; border: none; color: #7f56d9; cursor: pointer; font-size: 14px; margin-bottom: 12px; }
.header-card { background: #f9fafb; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
.header-row { display: flex; gap: 32px; flex-wrap: wrap; }
.header-row > div { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: 13px; color: #667085; }
.score { font-size: 24px; font-weight: 700; }
.status { padding: 2px 8px; border-radius: 12px; font-size: 12px; background: #d1e9ff; color: #175cd3; }
.decision-tree { margin-bottom: 24px; }
.layer { border: 1px solid #eaecf0; border-radius: 10px; margin-bottom: 8px; overflow: hidden; }
.layer-header { display: flex; align-items: center; gap: 8px; padding: 12px 16px; cursor: pointer; background: #f9fafb; }
.layer-header:hover { background: #f2f4f7; }
.layer-icon { font-size: 18px; }
.layer-title { font-weight: 600; flex: 1; }
.layer-score { font-size: 13px; color: #667085; }
.expand-icon { font-size: 12px; color: #98a2b3; }
.layer-body { padding: 0 16px 16px; }
.evidence-card { background: #fff; border: 1px solid #eaecf0; border-radius: 8px; padding: 12px; }
.evidence-card p { margin: 4px 0; font-size: 14px; }
.evidence-card code { background: #f2f4f7; padding: 2px 6px; border-radius: 4px; }
.action-panel { border: 1px solid #eaecf0; border-radius: 10px; padding: 20px; }
.action-panel h3 { margin-bottom: 12px; }
.action-panel textarea { width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #d0d5dd; resize: vertical; margin-bottom: 12px; box-sizing: border-box; }
.btn-group { display: flex; gap: 8px; }
.btn { padding: 8px 16px; border-radius: 6px; border: 1px solid #d0d5dd; background: #fff; cursor: pointer; font-size: 14px; }
.btn:disabled { opacity: 0.5; }
.btn-ok { background: #7f56d9; color: #fff; border-color: #7f56d9; }
.btn-err { background: #d92d20; color: #fff; border-color: #d92d20; }
.btn-warn { background: #f79009; color: #fff; border-color: #f79009; }
.error { color: #d92d20; padding: 40px; text-align: center; }
</style>
