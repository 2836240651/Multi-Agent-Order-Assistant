<script setup>
/**
 * 客服视图：工单列表 + 对话控制台入口。
 */
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { authStore } from "../../stores/auth.js";

const router = useRouter();
const stats = ref({ open: 0, pending: 0, closed: 0 });
const recentTickets = ref([]);

onMounted(() => {
  // Mock 数据，接入后端后替换
  stats.value = { open: 12, pending: 5, closed: 43 };
  recentTickets.value = [
    { id: "T-001", customer: "customer_a", subject: "耳机质量问题退款", status: "open", created: "10分钟前" },
    { id: "T-002", customer: "customer_b", subject: "订单地址修改", status: "pending", created: "30分钟前" },
    { id: "T-003", customer: "customer_c", subject: "七天无理由退货咨询", status: "open", created: "1小时前" },
  ];
});

function openChat() {
  router.push("/chat");
}
</script>

<template>
  <div class="agent-dashboard">
    <header class="page-header">
      <h1>客服工作台</h1>
      <span class="welcome">欢迎，{{ authStore.user?.display_name || '客服' }}</span>
    </header>

    <div class="stats-row">
      <div class="stat-card open">
        <div class="stat-num">{{ stats.open }}</div>
        <div class="stat-label">待处理</div>
      </div>
      <div class="stat-card pending">
        <div class="stat-num">{{ stats.pending }}</div>
        <div class="stat-label">处理中</div>
      </div>
      <div class="stat-card closed">
        <div class="stat-num">{{ stats.closed }}</div>
        <div class="stat-label">已完成</div>
      </div>
    </div>

    <section class="section">
      <div class="section-header">
        <h2>最近工单</h2>
        <button class="btn-primary" @click="openChat">打开对话控制台</button>
      </div>
      <table class="ticket-table">
        <thead>
          <tr><th>工单号</th><th>客户</th><th>主题</th><th>状态</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="t in recentTickets" :key="t.id">
            <td>{{ t.id }}</td>
            <td>{{ t.customer }}</td>
            <td>{{ t.subject }}</td>
            <td><span :class="['badge', t.status]">{{ t.status }}</span></td>
            <td>{{ t.created }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.agent-dashboard { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 22px; margin: 0; }
.welcome { color: #888; font-size: 14px; }
.stats-row { display: flex; gap: 16px; margin-bottom: 24px; }
.stat-card { flex: 1; padding: 20px; border-radius: 10px; text-align: center; background: #f8f9fa; }
.stat-card.open { border-left: 4px solid #ff6b6b; }
.stat-card.pending { border-left: 4px solid #ffa94d; }
.stat-card.closed { border-left: 4px solid #51cf66; }
.stat-num { font-size: 28px; font-weight: 700; }
.stat-label { color: #888; font-size: 13px; margin-top: 4px; }
.section { background: #fff; border-radius: 10px; padding: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.section-header h2 { font-size: 16px; margin: 0; }
.btn-primary { padding: 8px 16px; background: #667eea; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
.ticket-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ticket-table th, .ticket-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.badge.open { background: #fff3f3; color: #ff6b6b; }
.badge.pending { background: #fff4e6; color: #ffa94d; }
.badge.closed { background: #ebfbee; color: #51cf66; }
</style>
