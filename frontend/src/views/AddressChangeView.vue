<script setup>
/**
 * 顾客视图：改地址申请。
 * 选择订单 → 填写新地址 → 第一次确认 → Interrupt 二次确认 → 提交。
 */
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api.js";

const route = useRoute();
const router = useRouter();

const orders = ref([]);
const orderNo = ref(route.query.order_no || "");
const newAddress = ref("");
const step = ref(1); // 1=填表, 2=第一次确认, 3=提交中, 4=结果
const result = ref(null);
const error = ref("");

onMounted(async () => {
  try {
    // 只列出 pending/shipped 状态的订单（可改地址）
    const resp = await api.listOrders({ status: "pending", page_size: 50 });
    const resp2 = await api.listOrders({ status: "shipped", page_size: 50 });
    orders.value = [...(resp.data.orders || []), ...(resp2.data.orders || [])];
  } catch {}
});

function nextStep() {
  if (!orderNo.value) { error.value = "请选择订单"; return; }
  if (!newAddress.value.trim()) { error.value = "请填写新地址"; return; }
  error.value = "";
  step.value = 2;
}

function goBack() {
  step.value = 1;
}

async function confirmAndSubmit() {
  step.value = 3;
  error.value = "";
  try {
    // 通过 chat 端点发送改地址请求（走 agent 流程 + Interrupt）
    const resp = await api.createRefund({
      order_no: orderNo.value,
      reason: "address_change",
      description: `改地址：${newAddress.value}`,
    });
    result.value = resp.data;
    step.value = 4;
  } catch (e) {
    error.value = e.response?.data?.message || "提交失败，请稍后重试";
    step.value = 2;
  }
}
</script>

<template>
  <div class="address-change-page">
    <h2>申请改地址</h2>

    <!-- 步骤 4: 结果 -->
    <div v-if="step === 4 && result" class="result-card success">
      <div class="result-icon">✓</div>
      <h3>申请已提交</h3>
      <p>工单编号：<strong>{{ result.ticket_no }}</strong></p>
      <p class="note">系统将对地址变更进行审核，审核通过后自动更新。</p>
      <button class="btn" @click="router.push('/orders')">返回订单列表</button>
    </div>

    <!-- 步骤 1: 填写 -->
    <template v-if="step === 1">
      <div v-if="error" class="error-msg">{{ error }}</div>

      <div class="form-group">
        <label>选择订单 *</label>
        <select v-model="orderNo">
          <option value="">请选择订单</option>
          <option v-for="o in orders" :key="o.order_no" :value="o.order_no">
            {{ o.order_no }} — {{ o.product_name || "商品" }} — 当前地址: {{ o.shipping_address || "未填写" }}
          </option>
        </select>
      </div>

      <div class="form-group">
        <label>新收货地址 *</label>
        <textarea v-model="newAddress" rows="3" placeholder="请填写完整的新收货地址" />
      </div>

      <div class="form-actions">
        <button class="btn btn-accent" @click="nextStep">下一步：确认</button>
        <button class="btn" @click="router.back()">取消</button>
      </div>
    </template>

    <!-- 步骤 2: 双重确认（Interrupt 模拟） -->
    <template v-if="step === 2">
      <div class="confirm-card">
        <div class="confirm-icon">⚠️</div>
        <h3>请确认地址变更</h3>
        <div class="confirm-detail">
          <div class="row"><span class="label">订单号</span><span>{{ orderNo }}</span></div>
          <div class="row"><span class="label">新地址</span><span class="new-addr">{{ newAddress }}</span></div>
        </div>
        <p class="confirm-warn">地址变更将触发系统审核，确认后不可撤回。请核实新地址是否正确。</p>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <div class="form-actions">
          <button class="btn btn-accent" :disabled="step === 3" @click="confirmAndSubmit">
            {{ step === 3 ? "提交中..." : "确认提交" }}
          </button>
          <button class="btn" @click="goBack">返回修改</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.address-change-page { padding: 24px; max-width: 600px; margin: 0 auto; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; margin-bottom: 6px; font-weight: 500; color: #344054; }
.form-group select, .form-group textarea { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid #d0d5dd; box-sizing: border-box; font-size: 14px; }
.form-group textarea { resize: vertical; }
.form-actions { display: flex; gap: 12px; margin-top: 20px; }
.btn { padding: 10px 20px; border-radius: 6px; border: 1px solid #d0d5dd; background: #fff; cursor: pointer; font-size: 14px; }
.btn:disabled { opacity: 0.5; }
.btn-accent { background: #7f56d9; color: #fff; border-color: #7f56d9; }
.error-msg { background: #fee4e2; color: #b42318; padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; }
.confirm-card { background: #fef0c7; border: 1px solid #f79009; border-radius: 10px; padding: 24px; text-align: center; }
.confirm-icon { font-size: 36px; margin-bottom: 8px; }
.confirm-card h3 { margin-bottom: 16px; }
.confirm-detail { background: #fff; border-radius: 8px; padding: 16px; text-align: left; margin-bottom: 16px; }
.confirm-detail .row { display: flex; padding: 6px 0; }
.confirm-detail .label { width: 70px; color: #667085; flex-shrink: 0; }
.confirm-detail .new-addr { color: #7f56d9; font-weight: 600; }
.confirm-warn { color: #b54708; font-size: 13px; margin-bottom: 16px; }
.result-card { text-align: center; padding: 40px 20px; }
.result-icon { width: 56px; height: 56px; border-radius: 50%; background: #d1fadf; color: #027a48; font-size: 28px; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }
.result-card h3 { margin-bottom: 12px; }
.result-card p { margin: 4px 0; color: #344054; }
.result-card .note { color: #667085; margin-top: 12px; font-size: 14px; }
</style>
