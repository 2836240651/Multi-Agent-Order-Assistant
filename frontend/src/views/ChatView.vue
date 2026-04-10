<script setup>
import { computed, reactive, ref } from "vue";
import { api } from "../api";
import { useToast } from "../composables/useToast";
import LoadingSpinner from "../components/LoadingSpinner.vue";
import EmptyState from "../components/EmptyState.vue";

const toast = useToast();

const chatForm = reactive({
  message: "我要申请退款，订单号 ORD-20260402-0002，因为不想要了",
  user_id: "demo-user",
  rollout_variant: "current_v3",
});

const chatResult = ref(null);
const loading = reactive({ chat: false });

const variants = [
  { value: "baseline_v1", label: "基线版本 v1" },
  { value: "optimized_v2", label: "优化版本 v2" },
  { value: "current_v3", label: "当前版本 v3" },
];

const demoCases = [
  { key: "order_success", label: "查单成功", icon: "🔍" },
  { key: "refund_success", label: "退款成功", icon: "💰" },
  { key: "refund_high_risk", label: "高风险退款", icon: "⚠️" },
  { key: "refund_failed", label: "退款失败", icon: "❌" },
  { key: "address_success", label: "改地址成功", icon: "📦" },
  { key: "address_failed", label: "改地址失败", icon: "🚫" },
  { key: "pii_review", label: "PII 检测", icon: "🔐" },
];

async function submitChat() {
  if (!chatForm.message.trim()) {
    toast.warning("请输入消息内容");
    return;
  }
  loading.chat = true;
  try {
    chatResult.value = await api.chat(chatForm);
    toast.success("请求发送成功");
  } catch (error) {
    toast.error(`请求失败: ${error.message}`);
  } finally {
    loading.chat = false;
  }
}

async function runDemo(caseName) {
  loading.chat = true;
  try {
    chatResult.value = await api.runCase(caseName, chatForm.rollout_variant);
    toast.success(`演示用例 [${caseName}] 执行成功`);
  } catch (error) {
    toast.error(`演示失败: ${error.message}`);
  } finally {
    loading.chat = false;
  }
}

async function resetDemo() {
  try {
    await api.resetDemo();
    chatResult.value = null;
    toast.success("Demo 已重置");
  } catch (error) {
    toast.error(`重置失败: ${error.message}`);
  }
}

const releaseInfo = computed(() => chatResult.value?.release || {});
const workflow = computed(() => chatResult.value?.workflow || {});
const risk = computed(() => chatResult.value?.risk || {});
const orderInfo = computed(() => workflow.value.result || {});

function getStatusType(status) {
  if (status === "executed" || status === "completed") return "success";
  if (status === "failed" || status === "degraded_fallback") return "danger";
  if (status === "pending_confirmation" || status === "pending_manual_review") return "warn";
  return "default";
}

function getOrderStatusInfo(status) {
  const statusMap = {
    pending: { label: "待处理", type: "warn", icon: "⏳" },
    processing: { label: "处理中", type: "info", icon: "🔄" },
    shipped: { label: "已发货", type: "info", icon: "🚚" },
    delivered: { label: "已送达", type: "success", icon: "✅" },
    completed: { label: "已完成", type: "success", icon: "🎉" },
    refunded: { label: "已退款", type: "danger", icon: "💸" },
    cancelled: { label: "已取消", type: "danger", icon: "❌" },
  };
  return statusMap[status] || { label: status, type: "default", icon: "📋" };
}

function getActionLabel(action) {
  const map = {
    order_query: "订单查询",
    refund_apply: "退款申请",
    order_update_address: "修改地址",
    ticket_create: "创建工单",
    ticket_update: "更新工单",
  };
  return map[action] || action;
}
</script>

<template>
  <div class="chat-view">
    <header class="view-header">
      <div>
        <h1>对话控制台</h1>
        <p>向多智能体系统发送请求，查看执行结果</p>
      </div>
      <button class="ghost-button" @click="resetDemo">重置 Demo</button>
    </header>

    <div class="chat-layout">
      <section class="panel chat-form-panel">
        <div class="panel-section">
          <h3>📝 发送请求</h3>
          <div class="form-grid">
            <label class="form-item">
              <span class="label-text">用户ID</span>
              <input v-model="chatForm.user_id" placeholder="输入用户ID" />
            </label>
            <label class="form-item">
              <span class="label-text">灰度版本</span>
              <select v-model="chatForm.rollout_variant">
                <option v-for="v in variants" :key="v.value" :value="v.value">
                  {{ v.label }}
                </option>
              </select>
            </label>
          </div>

          <label class="message-field">
            <span class="label-text">消息内容</span>
            <textarea
              v-model="chatForm.message"
              rows="4"
              placeholder="输入您的请求..."
            />
          </label>

          <div class="action-row">
            <button class="primary-button" :disabled="loading.chat" @click="submitChat">
              <LoadingSpinner v-if="loading.chat" size="16px" color="#fff" />
              <span v-if="loading.chat">处理中...</span>
              <span v-else>🚀 发送请求</span>
            </button>
          </div>
        </div>

        <div class="demo-section">
          <h4>⚡ 快速演示用例</h4>
          <div class="demo-grid">
            <button
              v-for="c in demoCases"
              :key="c.key"
              class="demo-btn"
              :disabled="loading.chat"
              @click="runDemo(c.key)"
            >
              <span class="demo-icon">{{ c.icon }}</span>
              <span class="demo-label">{{ c.label }}</span>
            </button>
          </div>
        </div>
      </section>

      <section class="panel chat-result-panel">
        <h3>📋 执行结果</h3>

        <div v-if="chatResult" class="result-content">
          <div class="result-meta">
            <span class="pill" :class="releaseInfo.degraded ? 'warn' : 'success'">
              {{ releaseInfo.variant }}
              {{ releaseInfo.degraded ? "(降级)" : "" }}
            </span>
            <span class="pill" :class="chatResult.compliance_passed ? 'success' : 'warn'">
              {{ chatResult.compliance_passed ? "✅ 合规通过" : "⚠️ 合规拦截" }}
            </span>
          </div>

          <div class="result-section">
            <h4>💬 系统回复</h4>
            <div class="response-box">{{ chatResult.response }}</div>
          </div>

          <div v-if="orderInfo.order_id" class="result-section">
            <h4>📦 订单信息</h4>
            <div class="order-card">
              <div class="order-header">
                <div class="order-id">
                  <span class="order-id-label">订单号</span>
                  <span class="order-id-value">{{ orderInfo.order_id }}</span>
                </div>
                <div class="order-status" :class="'status-' + getOrderStatusInfo(orderInfo.status).type">
                  <span class="status-icon">{{ getOrderStatusInfo(orderInfo.status).icon }}</span>
                  <span class="status-text">{{ getOrderStatusInfo(orderInfo.status).label }}</span>
                </div>
              </div>

              <div class="order-details">
                <div class="order-detail-item">
                  <span class="detail-label">商品</span>
                  <span class="detail-value">{{ orderInfo.product || "-" }}</span>
                </div>
                <div class="order-detail-item">
                  <span class="detail-label">金额</span>
                  <span class="detail-value price">¥{{ orderInfo.amount || 0 }}</span>
                </div>
                <div class="order-detail-item">
                  <span class="detail-label">收货地址</span>
                  <span class="detail-value">{{ orderInfo.address || "-" }}</span>
                </div>
                <div class="order-detail-item">
                  <span class="detail-label">可修改地址</span>
                  <span class="detail-value" :class="orderInfo.can_update_address ? 'bool-yes' : 'bool-no'">
                    {{ orderInfo.can_update_address ? "是" : "否" }}
                  </span>
                </div>
                <div class="order-detail-item">
                  <span class="detail-label">可退款</span>
                  <span class="detail-value" :class="orderInfo.refund_eligible ? 'bool-yes' : 'bool-no'">
                    {{ orderInfo.refund_eligible ? "是" : "否" }}
                  </span>
                </div>
                <div v-if="orderInfo.refund_id" class="order-detail-item">
                  <span class="detail-label">退款单号</span>
                  <span class="detail-value">{{ orderInfo.refund_id }}</span>
                </div>
                <div v-if="orderInfo.ticket_id" class="order-detail-item">
                  <span class="detail-label">工单号</span>
                  <span class="detail-value">{{ orderInfo.ticket_id }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="result-grid">
            <div class="result-item">
              <span class="label">意图</span>
              <span class="value">{{ chatResult.intent || "-" }}</span>
            </div>
            <div class="result-item">
              <span class="label">动作</span>
              <span class="value">{{ getActionLabel(chatResult.action) }}</span>
            </div>
            <div class="result-item">
              <span class="label">执行状态</span>
              <span class="value" :class="'status-' + getStatusType(chatResult.execution_status)">
                {{ chatResult.execution_status }}
              </span>
            </div>
            <div class="result-item">
              <span class="label">工单ID</span>
              <span class="value mono">{{ chatResult.ticket_id || "-" }}</span>
            </div>
            <div class="result-item">
              <span class="label">耗时</span>
              <span class="value">{{ chatResult.processing_ms }} ms</span>
            </div>
            <div class="result-item">
              <span class="label">成本</span>
              <span class="value">${{ chatResult.cost?.estimated_cost_usd || 0 }}</span>
            </div>
          </div>

          <div v-if="risk.risk_level" class="result-section">
            <h4>🛡️ 风险评估</h4>
            <div class="risk-cards">
              <span class="risk-badge" :class="'risk-' + risk.risk_level">
                {{ risk.risk_level === "high" ? "🔴 高风险" : risk.risk_level === "medium" ? "🟡 中风险" : "🟢 低风险" }}
              </span>
              <span v-if="risk.requires_manual_review" class="risk-badge warn">
                需要人工复核
              </span>
            </div>
            <ul v-if="risk.reasons?.length" class="risk-reasons">
              <li v-for="(reason, idx) in risk.reasons" :key="idx">{{ reason }}</li>
            </ul>
          </div>

          <details class="trace-details">
            <summary>🔍 完整 Trace 信息</summary>
            <pre class="json-pre">{{ JSON.stringify(chatResult.trace, null, 2) }}</pre>
          </details>
        </div>
        <EmptyState v-else icon="💬" title="暂无执行结果" description="发送请求后结果将显示在这里" />
      </section>
    </div>
  </div>
</template>
