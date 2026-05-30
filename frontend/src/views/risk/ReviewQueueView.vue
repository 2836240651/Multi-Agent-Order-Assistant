<script setup>
/**
 * 风控视图：待审队列 + 决策链展示 + Approve/Reject/Escalate。
 */
import { ref, onMounted } from "vue";
import { api } from "../../api.js";
import { authStore } from "../../stores/auth.js";

const queue = ref([]);
const selected = ref(null);
const reviewerNote = ref("");
const loading = ref(false);

onMounted(() => {
  // Mock 数据，接入后端后替换
  queue.value = [
    {
      thread_id: "th-001",
      customer: "customer_a",
      action: "退款 ¥999",
      fusion_score: 72.5,
      decision: "review",
      explanation: "规则命中：高额退款（R-001）；特征异常：amount_zscore",
      rules_hits: [{ rule_id: "R-001", description: "金额超过 500 元", severity: "high" }],
      created: "5分钟前",
    },
    {
      thread_id: "th-002",
      customer: "customer_d",
      action: "退款 ¥2999",
      fusion_score: 88.0,
      decision: "review",
      explanation: "规则命中：高额退款 + 新用户高金额；LLM 评估：高风险",
      rules_hits: [
        { rule_id: "R-001", description: "金额超过 500 元", severity: "high" },
        { rule_id: "R-007", description: "新用户高额退款", severity: "medium" },
      ],
      created: "12分钟前",
    },
  ];
});

function selectItem(item) {
  selected.value = item;
  reviewerNote.value = "";
}

async function approve() {
  if (!selected.value) return;
  loading.value = true;
  try {
    await api.reviewResume(selected.value.thread_id, "approve", reviewerNote.value);
    queue.value = queue.value.filter((q) => q.thread_id !== selected.value.thread_id);
    selected.value = null;
  } catch (e) {
    alert("审批失败: " + e.message);
  } finally {
    loading.value = false;
  }
}

async function reject() {
  if (!selected.value) return;
  loading.value = true;
  try {
    await api.reviewResume(selected.value.thread_id, "reject", reviewerNote.value);
    queue.value = queue.value.filter((q) => q.thread_id !== selected.value.thread_id);
    selected.value = null;
  } catch (e) {
    alert("拒绝失败: " + e.message);
  } finally {
    loading.value = false;
  }
}

async function escalate() {
  if (!selected.value) return;
  loading.value = true;
  try {
    await api.reviewResume(selected.value.thread_id, "escalate", reviewerNote.value);
    queue.value = queue.value.filter((q) => q.thread_id !== selected.value.thread_id);
    selected.value = null;
  } catch (e) {
    alert("升级失败: " + e.message);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="review-queue">
    <header class="page-header">
      <h1>风控审核队列</h1>
      <span class="count">{{ queue.length }} 条待审</span>
    </header>

    <div class="content-row">
      <!-- 左侧队列 -->
      <div class="queue-list">
        <div
          v-for="item in queue"
          :key="item.thread_id"
          class="queue-item"
          :class="{ active: selected?.thread_id === item.thread_id }"
          @click="selectItem(item)"
        >
          <div class="qi-header">
            <span class="qi-action">{{ item.action }}</span>
            <span class="qi-score" :class="{ high: item.fusion_score >= 60 }">
              {{ item.fusion_score.toFixed(1) }}
            </span>
          </div>
          <div class="qi-meta">
            <span>{{ item.customer }}</span>
            <span>{{ item.created }}</span>
          </div>
        </div>
        <div v-if="queue.length === 0" class="empty">暂无待审工单</div>
      </div>

      <!-- 右侧详情 -->
      <div class="detail-panel" v-if="selected">
        <h2>决策链 — {{ selected.thread_id }}</h2>

        <div class="decision-chain">
          <div class="chain-section">
            <h3>融合评分</h3>
            <div class="score-display">{{ selected.fusion_score.toFixed(1) }} / 100</div>
          </div>

          <div class="chain-section">
            <h3>规则命中</h3>
            <div v-for="hit in selected.rules_hits" :key="hit.rule_id" class="rule-hit">
              <span class="rule-id">{{ hit.rule_id }}</span>
              <span>{{ hit.description }}</span>
              <span :class="['severity', hit.severity]">{{ hit.severity }}</span>
            </div>
          </div>

          <div class="chain-section">
            <h3>解释</h3>
            <p class="explanation">{{ selected.explanation }}</p>
          </div>
        </div>

        <div class="reviewer-input">
          <textarea v-model="reviewerNote" placeholder="审核备注（可选）" rows="2"></textarea>
          <div class="action-buttons">
            <button class="btn-approve" @click="approve" :disabled="loading">通过</button>
            <button class="btn-reject" @click="reject" :disabled="loading">拒绝</button>
            <button class="btn-escalate" @click="escalate" :disabled="loading">升级转人工</button>
          </div>
        </div>
      </div>

      <div class="detail-panel empty-detail" v-else>
        <p>← 选择左侧工单查看决策链</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-queue { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h1 { font-size: 22px; margin: 0; }
.count { color: #ff6b6b; font-weight: 600; }
.content-row { display: flex; gap: 20px; min-height: 500px; }
.queue-list { width: 340px; flex-shrink: 0; background: #fff; border-radius: 10px; padding: 12px; overflow-y: auto; }
.queue-item { padding: 12px; border-radius: 8px; cursor: pointer; margin-bottom: 8px; border: 1px solid #eee; transition: all 0.15s; }
.queue-item:hover { border-color: #667eea; }
.queue-item.active { border-color: #667eea; background: #f0f2ff; }
.qi-header { display: flex; justify-content: space-between; align-items: center; }
.qi-action { font-weight: 600; font-size: 14px; }
.qi-score { font-weight: 700; color: #51cf66; }
.qi-score.high { color: #ff6b6b; }
.qi-meta { display: flex; justify-content: space-between; font-size: 12px; color: #999; margin-top: 6px; }
.empty { text-align: center; color: #ccc; padding: 40px; }
.detail-panel { flex: 1; background: #fff; border-radius: 10px; padding: 20px; }
.detail-panel h2 { font-size: 16px; margin: 0 0 16px; }
.empty-detail { display: flex; align-items: center; justify-content: center; color: #ccc; }
.decision-chain { margin-bottom: 20px; }
.chain-section { margin-bottom: 16px; }
.chain-section h3 { font-size: 13px; color: #888; margin: 0 0 8px; }
.score-display { font-size: 32px; font-weight: 700; color: #ff6b6b; }
.rule-hit { display: flex; gap: 8px; align-items: center; padding: 6px 10px; background: #fff4e6; border-radius: 6px; margin-bottom: 6px; font-size: 13px; }
.rule-id { font-weight: 700; color: #e67700; min-width: 48px; }
.severity { padding: 1px 6px; border-radius: 4px; font-size: 11px; }
.severity.high { background: #ffc9c9; color: #c92a2a; }
.severity.medium { background: #ffe8cc; color: #e67700; }
.explanation { font-size: 13px; color: #555; line-height: 1.6; margin: 0; }
.reviewer-input textarea { width: 100%; border: 1px solid #ddd; border-radius: 6px; padding: 8px; font-size: 13px; resize: vertical; }
.action-buttons { display: flex; gap: 8px; margin-top: 10px; }
.action-buttons button { flex: 1; padding: 10px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
.btn-approve { background: #51cf66; color: #fff; }
.btn-reject { background: #ff6b6b; color: #fff; }
.btn-escalate { background: #ffa94d; color: #fff; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
