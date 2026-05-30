<script setup>
/**
 * 客户视图：订单列表。
 * 筛选栏（状态）+ 表格 + 分页，点击行跳转详情/退款/对话。
 */
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import LoadingSpinner from "../components/LoadingSpinner.vue";
import EmptyState from "../components/EmptyState.vue";

const router = useRouter();
const orders = ref([]);
const total = ref(0);
const loading = ref(false);
const page = ref(1);
const pageSize = 20;
const filterStatus = ref("");

async function loadOrders() {
  loading.value = true;
  try {
    const params = { page: page.value, page_size: pageSize };
    if (filterStatus.value) params.status = filterStatus.value;
    const resp = await api.listOrders(params);
    orders.value = resp.data.orders || [];
    total.value = resp.data.total || 0;
  } catch {
    orders.value = [];
  } finally {
    loading.value = false;
  }
}

function onPageChange(p) {
  page.value = p;
  loadOrders();
}

function viewDetail(orderNo) {
  router.push(`/orders/${orderNo}`);
}

function applyRefund(orderNo) {
  router.push({ path: "/refund", query: { order_no: orderNo } });
}

function startChat(orderNo) {
  router.push({ path: "/chat", query: { order_no: orderNo } });
}

function changeAddress(orderNo) {
  router.push({ path: "/address-change", query: { order_no: orderNo } });
}

const statusLabel = {
  pending: "待支付",
  paid: "已支付",
  shipped: "已发货",
  delivered: "已签收",
  cancelled: "已取消",
};
const statusClass = {
  pending: "badge-warn",
  paid: "badge-info",
  shipped: "badge-info",
  delivered: "badge-ok",
  cancelled: "badge-err",
};

onMounted(loadOrders);
</script>

<template>
  <div class="order-list-page">
    <h2>我的订单</h2>

    <div class="filter-bar">
      <select v-model="filterStatus" @change="page = 1; loadOrders()">
        <option value="">全部状态</option>
        <option value="pending">待支付</option>
        <option value="paid">已支付</option>
        <option value="shipped">已发货</option>
        <option value="delivered">已签收</option>
        <option value="cancelled">已取消</option>
      </select>
      <span class="total-label">共 {{ total }} 条</span>
    </div>

    <LoadingSpinner v-if="loading" size="32px" />

    <EmptyState v-else-if="orders.length === 0" title="暂无订单" description="您还没有任何订单记录" />

    <template v-else>
      <table class="data-table">
        <thead>
          <tr>
            <th>订单号</th>
            <th>商品</th>
            <th>金额</th>
            <th>件数</th>
            <th>状态</th>
            <th>下单时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <td class="link" @click="viewDetail(o.order_no)">{{ o.order_no }}</td>
            <td>{{ o.product_name || "—" }}</td>
            <td>¥{{ (o.total_amount || 0).toFixed(2) }}</td>
            <td>{{ o.item_count }}</td>
            <td><span class="badge" :class="statusClass[o.status]">{{ statusLabel[o.status] || o.status }}</span></td>
            <td>{{ o.created_at?.slice(0, 16) }}</td>
            <td class="actions">
              <button class="btn-sm" @click="viewDetail(o.order_no)">详情</button>
              <button class="btn-sm btn-accent" v-if="o.status === 'delivered'" @click="applyRefund(o.order_no)">退款</button>
              <button class="btn-sm btn-warn" v-if="['pending','shipped'].includes(o.status)" @click="changeAddress(o.order_no)">改地址</button>
              <button class="btn-sm" @click="startChat(o.order_no)">咨询</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="pagination" v-if="total > pageSize">
        <button :disabled="page <= 1" @click="onPageChange(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ Math.ceil(total / pageSize) }} 页</span>
        <button :disabled="page >= Math.ceil(total / pageSize)" @click="onPageChange(page + 1)">下一页</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.order-list-page { padding: 24px; max-width: 1100px; margin: 0 auto; }
.filter-bar { display: flex; align-items: center; gap: 12px; margin: 16px 0; }
.filter-bar select { padding: 6px 10px; border-radius: 6px; border: 1px solid #d0d5dd; }
.total-label { color: #667085; font-size: 14px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.data-table th, .data-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #eaecf0; }
.data-table th { background: #f9fafb; color: #667085; font-weight: 600; }
.link { color: #7f56d9; cursor: pointer; }
.link:hover { text-decoration: underline; }
.badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.badge-ok { background: #d1fadf; color: #027a48; }
.badge-info { background: #d1e9ff; color: #175cd3; }
.badge-warn { background: #fef0c7; color: #b54708; }
.badge-err { background: #fee4e2; color: #b42318; }
.actions { display: flex; gap: 6px; }
.btn-sm { padding: 4px 10px; border-radius: 6px; border: 1px solid #d0d5dd; background: #fff; cursor: pointer; font-size: 13px; }
.btn-sm:hover { background: #f2f4f7; }
.btn-accent { border-color: #7f56d9; color: #7f56d9; }
.btn-warn { border-color: #f79009; color: #f79009; }
.pagination { display: flex; align-items: center; gap: 12px; margin-top: 16px; justify-content: center; }
.pagination button { padding: 6px 14px; border-radius: 6px; border: 1px solid #d0d5dd; background: #fff; cursor: pointer; }
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
