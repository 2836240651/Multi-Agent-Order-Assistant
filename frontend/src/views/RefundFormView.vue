<script setup>
/**
 * 客户视图：退款申请表单。
 * 选择订单 → 填写原因/描述 → 提交 → 展示结果。
 */
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api.js";

const route = useRoute();
const router = useRouter();

const orders = ref([]);
const orderNo = ref(route.query.order_no || "");
const reason = ref("");
const description = ref("");
const submitting = ref(false);
const result = ref(null);
const error = ref("");

const reasons = [
  "商品质量问题",
  "与描述不符",
  "发错货",
  "少件/漏发",
  "不想要了",
  "其他",
];

onMounted(async () => {
  try {
    const resp = await api.listOrders({ status: "delivered", page_size: 100 });
    orders.value = resp.data.orders || [];
  } catch {}
});

async function submit() {
  if (!orderNo.value || !reason.value) {
    error.value = "请选择订单和退款原因";
    return;
  }
  error.value = "";
  submitting.value = true;
  try {
    const resp = await api.createRefund({
      order_no: orderNo.value,
      reason: reason.value,
      description: description.value,
    });
    result.value = resp.data;
  } catch (e) {
    error.value = e.response?.data?.message || "申请失败，请稍后重试";
  } finally {
    submitting.value = false;
  }
}

function goOrders() {
  router.push("/orders");
}
</script>

<template>
  <div class="refund-form-page">
    <h2>申请退款</h2>

    <!-- 成功结果 -->
    <div v-if="result" class="result-card success">
      <div class="result-icon">✓</div>
      <h3>申请提交成功</h3>
      <p>退款编号：<strong>{{ result.refund_no }}</strong></p>
      <p>工单编号：<strong>{{ result.ticket_no }}</strong></p>
      <p>退款金额：<strong>¥{{ (result.amount || 0).toFixed(2) }}</strong></p>
      <p class="note">我们将在 1-3 个工作日内处理您的退款申请。</p>
      <button class="btn" @click="goOrders">返回订单列表</button>
    </div>

    <!-- 申请表单 -->
    <template v-else>
      <div v-if="error" class="error-msg">{{ error }}</div>

      <div class="form-group">
        <label>选择订单 *</label>
        <select v-model="orderNo">
          <option value="">请选择订单</option>
          <option v-for="o in orders" :key="o.order_no" :value="o.order_no">
            {{ o.order_no }} — {{ o.product_name || "商品" }} — ¥{{ (o.total_amount || 0).toFixed(2) }}
          </option>
        </select>
      </div>

      <div class="form-group">
        <label>退款原因 *</label>
        <select v-model="reason">
          <option value="">请选择原因</option>
          <option v-for="r in reasons" :key="r" :value="r">{{ r }}</option>
        </select>
      </div>

      <div class="form-group">
        <label>详细说明</label>
        <textarea v-model="description" rows="4" placeholder="请描述退款原因（选填）" />
      </div>

      <div class="form-actions">
        <button class="btn btn-accent" :disabled="submitting" @click="submit">
          {{ submitting ? "提交中..." : "提交退款申请" }}</button>
        <button class="btn" @click="goOrders">取消</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.refund-form-page { padding: 24px; max-width: 600px; margin: 0 auto; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; margin-bottom: 6px; font-weight: 500; color: #344054; }
.form-group select, .form-group textarea { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid #d0d5dd; box-sizing: border-box; font-size: 14px; }
.form-group textarea { resize: vertical; }
.form-actions { display: flex; gap: 12px; margin-top: 20px; }
.btn { padding: 10px 20px; border-radius: 6px; border: 1px solid #d0d5dd; background: #fff; cursor: pointer; font-size: 14px; }
.btn:disabled { opacity: 0.5; }
.btn-accent { background: #7f56d9; color: #fff; border-color: #7f56d9; }
.error-msg { background: #fee4e2; color: #b42318; padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; }
.result-card { text-align: center; padding: 40px 20px; }
.result-icon { width: 56px; height: 56px; border-radius: 50%; background: #d1fadf; color: #027a48; font-size: 28px; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }
.result-card h3 { margin-bottom: 12px; }
.result-card p { margin: 4px 0; color: #344054; }
.result-card .note { color: #667085; margin-top: 12px; font-size: 14px; }
</style>
