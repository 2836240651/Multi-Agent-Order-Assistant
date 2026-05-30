<script setup>
/**
 * 坐席视图：工单处理。
 * 展示工单详情 + 操作（accept/reject/escalate/close）+ 备注。
 */
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../../api.js";
import LoadingSpinner from "../../components/LoadingSpinner.vue";

const route = useRoute();
const router = useRouter();

const ticket = ref(null);
const loading = ref(true);
const note = ref("");
const action = ref("");
const acting = ref(false);

async function load() {
  loading.value = true;
  try {
    const resp = await api.getTicket(route.params.ticketNo);
    ticket.value = resp.data;
  } catch {
    ticket.value = null;
  } finally {
    loading.value = false;
  }
}

async function submitAction() {
  if (!action.value) return;
  if (["reject", "escalate"].includes(action.value) && !note.value.trim()) {
    alert("拒绝/升级时必须填写备注");
    return;
  }
  acting.value = true;
  try {
    await api.ticketAction(ticket.value.ticket_no, action.value, note.value);
    await load();
    action.value = "";
    note.value = "";
  } catch (e) {
    alert(e.response?.data?.message || "操作失败");
  } finally {
    acting.value = false;
  }
}

const statusMap = {
  open: "待处理", assigned: "已分配", processing: "处理中",
  waiting_review: "待审核", resolved: "已解决", rejected: "已拒绝", escalated: "已升级",
};
const typeMap = { refund: "退款", exchange: "换货", address_change: "地址变更" };
const actionOptions = [
  { value: "accept", label: "接受处理", color: "#7f56d9" },
  { value: "reject", label: "拒绝", color: "#d92d20" },
  { value: "escalate", label: "升级审核", color: "#f79009" },
  { value: "close", label: "关闭工单", color: "#667085" },
];

onMounted(load);
</script>

<template>
  <div class="ticket-handle-page">
    <button class="btn-back" @click="router.back()">← 返回</button>

    <LoadingSpinner v-if="loading" size="32px" />
    <div v-else-if="!ticket" class="error">工单不存在</div>

    <template v-else>
      <h2>工单处理 {{ ticket.ticket_no }}</h2>

      <div class="info-card">
        <div class="row"><span class="label">类型</span><span>{{ typeMap[ticket.type] || ticket.type }}</span></div>
        <div class="row"><span class="label">状态</span><span class="status-badge">{{ statusMap[ticket.status] || ticket.status }}</span></div>
        <div class="row"><span class="label">金额</span><span>¥{{ (ticket.amount || 0).toFixed(2) }}</span></div>
        <div class="row"><span class="label">原因</span><span>{{ ticket.reason || "—" }}</span></div>
        <div class="row"><span class="label">风险评分</span><span>{{ ticket.risk_score ?? "—" }}</span></div>
        <div class="row"><span class="label">创建时间</span><span>{{ ticket.created_at }}</span></div>
      </div>

      <div class="action-panel" v-if="!['resolved','rejected','closed'].includes(ticket.status)">
        <h3>操作</h3>
        <div class="action-options">
          <label v-for="opt in actionOptions" :key="opt.value" class="action-radio">
            <input type="radio" v-model="action" :value="opt.value" />
            <span class="radio-label" :style="{ borderColor: opt.color, color: action === opt.value ? opt.color : '' }">
              {{ opt.label }}
            </span>
          </label>
        </div>
        <textarea v-model="note" placeholder="处理备注" rows="3" />
        <button class="btn-submit" :disabled="acting || !action" @click="submitAction">
          {{ acting ? "处理中..." : "确认提交" }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ticket-handle-page { padding: 24px; max-width: 800px; margin: 0 auto; }
.btn-back { background: none; border: none; color: #7f56d9; cursor: pointer; font-size: 14px; margin-bottom: 12px; }
.info-card { background: #f9fafb; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
.row { display: flex; padding: 8px 0; border-bottom: 1px solid #eaecf0; }
.row:last-child { border-bottom: none; }
.label { width: 100px; color: #667085; font-weight: 500; flex-shrink: 0; }
.status-badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; background: #d1e9ff; color: #175cd3; }
.action-panel { border: 1px solid #eaecf0; border-radius: 10px; padding: 20px; }
.action-panel h3 { margin-bottom: 12px; }
.action-options { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.action-radio input { display: none; }
.radio-label { padding: 6px 14px; border-radius: 6px; border: 1px solid #d0d5dd; cursor: pointer; font-size: 14px; }
.action-radio input:checked + .radio-label { background: #f4f0ff; font-weight: 600; }
.action-panel textarea { width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #d0d5dd; resize: vertical; margin-bottom: 12px; box-sizing: border-box; }
.btn-submit { padding: 10px 24px; border-radius: 6px; border: none; background: #7f56d9; color: #fff; cursor: pointer; font-size: 14px; }
.btn-submit:disabled { opacity: 0.5; }
.error { color: #d92d20; padding: 40px; text-align: center; }
</style>
