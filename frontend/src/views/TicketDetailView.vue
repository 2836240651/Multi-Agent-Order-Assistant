<script setup>
/**
 * 客服/坐席视图：工单详情。
 * 展示工单信息 + 关联订单 + 操作按钮（accept/reject/escalate/close）。
 */
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api.js";
import { useAuth } from "../stores/auth.js";
import LoadingSpinner from "../components/LoadingSpinner.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuth();

const ticket = ref(null);
const loading = ref(true);
const actionNote = ref("");
const acting = ref(false);

const isAgent = auth.hasRole("agent") || auth.hasRole("admin");

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

async function doAction(action) {
  if (!actionNote.value && (action === "reject" || action === "escalate")) {
    alert("请填写操作备注");
    return;
  }
  acting.value = true;
  try {
    await api.ticketAction(ticket.value.ticket_no, action, actionNote.value);
    actionNote.value = "";
    await load();
  } catch (e) {
    alert(e.response?.data?.message || "操作失败");
  } finally {
    acting.value = false;
  }
}

const statusLabel = {
  open: "待处理",
  assigned: "已分配",
  processing: "处理中",
  waiting_review: "待审核",
  resolved: "已解决",
  rejected: "已拒绝",
  escalated: "已升级",
};
const typeLabel = {
  refund: "退款",
  exchange: "换货",
  address_change: "地址变更",
};

onMounted(load);
</script>

<template>
  <div class="ticket-detail-page">
    <button class="btn-back" @click="router.back()">← 返回</button>

    <LoadingSpinner v-if="loading" size="32px" />
    <div v-else-if="!ticket" class="error">工单不存在</div>

    <template v-else>
      <h2>工单 {{ ticket.ticket_no }}</h2>

      <div class="info-card">
        <div class="row"><span class="label">类型</span><span>{{ typeLabel[ticket.type] || ticket.type }}</span></div>
        <div class="row"><span class="label">状态</span><span class="badge">{{ statusLabel[ticket.status] || ticket.status }}</span></div>
        <div class="row"><span class="label">金额</span><span>¥{{ (ticket.amount || 0).toFixed(2) }}</span></div>
        <div class="row"><span class="label">原因</span><span>{{ ticket.reason || "—" }}</span></div>
        <div class="row"><span class="label">关联订单</span><span>{{ ticket.order_id || "—" }}</span></div>
        <div class="row"><span class="label">风险评分</span><span>{{ ticket.risk_score ?? "—" }}</span></div>
        <div class="row"><span class="label">创建时间</span><span>{{ ticket.created_at }}</span></div>
        <div class="row" v-if="ticket.closed_at"><span class="label">关闭时间</span><span>{{ ticket.closed_at }}</span></div>
      </div>

      <div class="actions-panel" v-if="isAgent && !['resolved','rejected','closed'].includes(ticket.status)">
        <h3>处理工单</h3>
        <textarea v-model="actionNote" placeholder="操作备注（拒绝/升级时必填）" rows="3" />
        <div class="btn-group">
          <button class="btn btn-ok" :disabled="acting" @click="doAction('accept')">接受处理</button>
          <button class="btn btn-err" :disabled="acting" @click="doAction('reject')">拒绝</button>
          <button class="btn btn-warn" :disabled="acting" @click="doAction('escalate')">升级审核</button>
          <button class="btn" :disabled="acting" @click="doAction('close')">关闭工单</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ticket-detail-page { padding: 24px; max-width: 800px; margin: 0 auto; }
.btn-back { background: none; border: none; color: #7f56d9; cursor: pointer; font-size: 14px; margin-bottom: 12px; }
.info-card { background: #f9fafb; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
.row { display: flex; padding: 8px 0; border-bottom: 1px solid #eaecf0; }
.row:last-child { border-bottom: none; }
.label { width: 100px; color: #667085; font-weight: 500; flex-shrink: 0; }
.badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; background: #d1e9ff; color: #175cd3; }
.actions-panel { background: #fff; border: 1px solid #eaecf0; border-radius: 10px; padding: 20px; }
.actions-panel h3 { margin-bottom: 12px; }
.actions-panel textarea { width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #d0d5dd; resize: vertical; margin-bottom: 12px; box-sizing: border-box; }
.btn-group { display: flex; gap: 8px; flex-wrap: wrap; }
.btn { padding: 8px 16px; border-radius: 6px; border: 1px solid #d0d5dd; background: #fff; cursor: pointer; font-size: 14px; }
.btn:disabled { opacity: 0.5; }
.btn-ok { background: #7f56d9; color: #fff; border-color: #7f56d9; }
.btn-err { background: #d92d20; color: #fff; border-color: #d92d20; }
.btn-warn { background: #f79009; color: #fff; border-color: #f79009; }
.error { color: #d92d20; padding: 40px; text-align: center; }
</style>
