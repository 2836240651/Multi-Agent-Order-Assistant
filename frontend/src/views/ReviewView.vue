<script setup>
import { onMounted, reactive, ref } from "vue";
import { api } from "../api";
import { useToast } from "../composables/useToast";
import LoadingSpinner from "../components/LoadingSpinner.vue";
import EmptyState from "../components/EmptyState.vue";

const toast = useToast();

const reviews = ref([]);
const reviewNote = ref("Approved by frontend console.");
const loading = reactive({ reviews: true, action: false });

async function loadReviews() {
  loading.reviews = true;
  try {
    const response = await api.pendingReviews();
    reviews.value = response.items || [];
  } catch (error) {
    toast.error(`加载失败: ${error.message}`);
  } finally {
    loading.reviews = false;
  }
}

async function approve(reviewId) {
  loading.action = true;
  try {
    await api.approveReview(reviewId, reviewNote.value);
    toast.success("审批通过，已执行操作");
    await loadReviews();
  } catch (error) {
    toast.error(`审批失败: ${error.message}`);
  } finally {
    loading.action = false;
  }
}

async function reject(reviewId) {
  loading.action = true;
  try {
    await api.rejectReview(reviewId, reviewNote.value);
    toast.warning("已拒绝该请求");
    await loadReviews();
  } catch (error) {
    toast.error(`操作失败: ${error.message}`);
  } finally {
    loading.action = false;
  }
}

function getRiskClass(level) {
  if (level === "high") return "danger";
  if (level === "medium") return "warn";
  return "default";
}

function getActionLabel(action) {
  const map = {
    refund_apply: "退款申请",
    order_update_address: "修改地址",
    order_query: "订单查询",
  };
  return map[action] || action;
}

onMounted(loadReviews);
</script>

<template>
  <div class="review-view">
    <header class="view-header">
      <div>
        <h1>人工复核队列</h1>
        <p>高风险请求在此等待人工审批后执行</p>
      </div>
      <button class="ghost-button" @click="loadReviews" :disabled="loading.reviews">
        <LoadingSpinner v-if="loading.reviews" size="14px" />
        <span v-if="loading.reviews">加载中...</span>
        <span v-else>🔄 刷新</span>
      </button>
    </header>

    <div class="review-content">
      <section class="panel">
        <div class="review-note-section">
          <label class="review-note-field">
            <span class="label-text">📝 审批备注 (通用)</span>
            <input v-model="reviewNote" placeholder="输入审批备注，将应用于所有审批操作" />
          </label>
        </div>

        <div v-if="reviews.length" class="review-list">
          <article v-for="item in reviews" :key="item.review_id" class="review-card">
            <div class="review-card-header">
              <div class="review-header-left">
                <span class="review-id">{{ item.review_id }}</span>
                <span class="risk-badge" :class="getRiskClass(item.risk_level)">
                  {{ item.risk_level === "high" ? "🔴 高风险" : item.risk_level === "medium" ? "🟡 中风险" : "🟢 低风险" }}
                </span>
              </div>
              <div class="review-meta">
                <span class="meta-tag">{{ getActionLabel(item.action) }}</span>
                <span class="meta-tag">工单: {{ item.ticket_id || "-" }}</span>
              </div>
            </div>

            <div class="review-card-body">
              <div v-if="item.order_info && item.order_info.refund_eligible === false" class="warning-banner">
                <span class="warning-icon">⚠️</span>
                <div class="warning-text">
                  <strong>退款时限预警</strong>
                  <p>该订单已超过退款时限（退款截止：{{ item.order_info.refund_deadline || '未知' }}），批准后退款将失败！</p>
                </div>
              </div>

              <p class="review-reason">
                <strong>风险原因：</strong>{{ item.reason }}
              </p>

              <div v-if="item.workflow_snapshot" class="workflow-snapshot">
                <div class="snapshot-header">
                  <span class="snapshot-title">📋 请求快照</span>
                </div>
                <p class="snapshot-message">"{{ item.workflow_snapshot.requested_message }}"</p>
                <div v-if="item.workflow_snapshot.entities" class="snapshot-entities">
                  <span
                    v-for="(val, key) in item.workflow_snapshot.entities"
                    :key="key"
                    class="entity-tag"
                  >
                    {{ key }}: {{ val }}
                  </span>
                </div>
              </div>
            </div>

            <div class="review-card-footer">
              <div class="review-note-preview">
                <span class="note-label">备注：</span>
                <span class="note-text">{{ reviewNote || "无" }}</span>
              </div>
              <div class="review-actions">
                <button
                  class="approve-btn"
                  :disabled="loading.action"
                  @click="approve(item.review_id)"
                >
                  <LoadingSpinner v-if="loading.action" size="14px" color="#fff" />
                  <span v-else>✅ 批准执行</span>
                </button>
                <button
                  class="reject-btn"
                  :disabled="loading.action"
                  @click="reject(item.review_id)"
                >
                  <LoadingSpinner v-if="loading.action" size="14px" color="#fff" />
                  <span v-else>❌ 拒绝</span>
                </button>
              </div>
            </div>
          </article>
        </div>
        <EmptyState
          v-else
          icon="✅"
          title="暂无待处理复核"
          description="所有高风险请求都已处理完毕"
        />
      </section>
    </div>
  </div>
</template>

<style scoped>
.warning-banner {
  display: flex;
  gap: 10px;
  padding: 12px;
  background: #fff3e0;
  border: 1px solid #ff9800;
  border-radius: 6px;
  margin-bottom: 12px;
}

.warning-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.warning-text {
  flex: 1;
}

.warning-text strong {
  color: #e65100;
  display: block;
  margin-bottom: 4px;
}

.warning-text p {
  margin: 0;
  color: #d84315;
  font-size: 13px;
}
</style>
