<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api";
import { useToast } from "../composables/useToast";
import LoadingSpinner from "../components/LoadingSpinner.vue";
import EmptyState from "../components/EmptyState.vue";

const toast = useToast();

const auditLogs = ref([]);
const loading = reactive({ audit: true });
const filterEventType = ref("");
const filterAction = ref("");

const pageSize = 20;
const currentPage = ref(1);

const eventTypes = [
  { value: "workflow_completed", label: "流程完成" },
  { value: "manual_review_requested", label: "人工复核请求" },
  { value: "manual_review_resolved", label: "人工复核处理" },
  { value: "workflow_degraded", label: "降级执行" },
];

const actions = [
  { value: "order_query", label: "订单查询" },
  { value: "refund_apply", label: "退款申请" },
  { value: "order_update_address", label: "修改地址" },
  { value: "manual_support", label: "人工支持" },
];

const filteredLogs = computed(() => {
  let logs = auditLogs.value;
  if (filterEventType.value) {
    logs = logs.filter((log) => log.event_type === filterEventType.value);
  }
  if (filterAction.value) {
    logs = logs.filter((log) => log.action === filterAction.value);
  }
  return logs.slice().reverse();
});

const paginatedLogs = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredLogs.value.slice(start, start + pageSize);
});

const totalPages = computed(() => {
  return Math.ceil(filteredLogs.value.length / pageSize) || 1;
});

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--;
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++;
  }
}

async function loadAuditLogs() {
  loading.audit = true;
  try {
    const response = await api.auditLogs();
    auditLogs.value = response.items || [];
    currentPage.value = 1;
  } catch (error) {
    toast.error(`加载失败: ${error.message}`);
  } finally {
    loading.audit = false;
  }
}

function formatTime(timestamp) {
  if (!timestamp) return "-";
  return new Date(timestamp).toLocaleString("zh-CN");
}

function getEventTypeLabel(type) {
  const item = eventTypes.find((t) => t.value === type);
  return item ? item.label : type;
}

function getActionLabel(action) {
  const item = actions.find((a) => a.value === action);
  return item ? item.label : action;
}

function getStatusClass(status) {
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  if (status === "pending") return "warn";
  return "default";
}

onMounted(loadAuditLogs);
</script>

<template>
  <div class="audit-view">
    <header class="view-header">
      <div>
        <h1>审计日志</h1>
        <p>系统证据链和关键运行事件的完整记录</p>
      </div>
      <button class="ghost-button" @click="loadAuditLogs" :disabled="loading.audit">
        <LoadingSpinner v-if="loading.audit" size="14px" />
        <span v-if="loading.audit">加载中...</span>
        <span v-else>🔄 刷新</span>
      </button>
    </header>

    <div class="audit-content">
      <section class="panel">
        <div class="filters-section">
          <div class="filters-row">
            <label class="filter-item">
              <span class="label-text">事件类型</span>
              <select v-model="filterEventType" @change="currentPage = 1">
                <option value="">全部类型</option>
                <option v-for="type in eventTypes" :key="type.value" :value="type.value">
                  {{ type.label }}
                </option>
              </select>
            </label>
            <label class="filter-item">
              <span class="label-text">动作</span>
              <select v-model="filterAction" @change="currentPage = 1">
                <option value="">全部动作</option>
                <option v-for="act in actions" :key="act.value" :value="act.value">
                  {{ act.label }}
                </option>
              </select>
            </label>
          </div>
          <div class="filter-summary">
            共 {{ filteredLogs.length }} 条记录
          </div>
        </div>

        <div v-if="loading.audit" class="loading-state">
          <LoadingSpinner size="32px" />
          <span>加载中...</span>
        </div>

        <div v-else-if="paginatedLogs.length" class="audit-table-wrap">
          <table class="audit-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>事件ID</th>
                <th>类型</th>
                <th>动作</th>
                <th>状态</th>
                <th>用户</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in paginatedLogs" :key="item.event_id + item.created_at">
                <td class="cell-time">{{ formatTime(item.created_at) }}</td>
                <td class="cell-id">{{ item.event_id?.slice(0, 12) }}...</td>
                <td>
                  <span class="type-tag">{{ getEventTypeLabel(item.event_type) }}</span>
                </td>
                <td class="cell-action">{{ getActionLabel(item.action) }}</td>
                <td>
                  <span class="status-pill" :class="getStatusClass(item.status)">
                    {{ item.status }}
                  </span>
                </td>
                <td class="cell-user">{{ item.user_id || "-" }}</td>
                <td class="cell-details">
                  <details class="detail-popup">
                    <summary>查看</summary>
                    <div class="detail-content">
                      <pre>{{ JSON.stringify(item.details || item.evidence || {}, null, 2) }}</pre>
                    </div>
                  </details>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="pagination">
            <button class="page-btn" :disabled="currentPage === 1" @click="prevPage">
              ‹ 上一页
            </button>
            <span class="page-info">
              第 {{ currentPage }} / {{ totalPages }} 页
            </span>
            <button class="page-btn" :disabled="currentPage === totalPages" @click="nextPage">
              下一页 ›
            </button>
          </div>
        </div>
        <EmptyState v-else icon="📋" title="暂无审计日志" description="没有符合筛选条件的日志记录" />
      </section>
    </div>
  </div>
</template>
