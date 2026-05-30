<script setup>
/**
 * 客服对话详情：从收件箱点入或直链 /agent/conversation/:threadId。
 */
import { ref, onMounted, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../../api.js";
import LoadingSpinner from "../../components/LoadingSpinner.vue";
import EmptyState from "../../components/EmptyState.vue";

const route = useRoute();
const router = useRouter();
const threadId = ref(route.params.threadId || "");
const messages = ref([]);
const loading = ref(false);
const messagesContainer = ref(null);

async function loadMessages() {
  if (!threadId.value) return;
  loading.value = true;
  try {
    const resp = await api.getThreadMessages(threadId.value);
    messages.value = resp.data.messages || [];
    await nextTick();
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  } catch {
    messages.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.params.threadId,
  (id) => {
    threadId.value = id || "";
    loadMessages();
  }
);

onMounted(loadMessages);
</script>

<template>
  <div class="conversation-page">
    <header class="conv-header">
      <button type="button" class="back-btn" @click="router.push('/agent/sessions')">← 收件箱</button>
      <h2>会话 {{ threadId?.slice(0, 12) }}</h2>
    </header>

    <LoadingSpinner v-if="loading" />
    <EmptyState v-else-if="!threadId" title="未指定会话" description="请从收件箱选择会话" />
    <div v-else class="conv-body">
      <div ref="messagesContainer" class="message-list">
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="msg-row"
          :class="m.role === 'user' ? 'user' : 'assistant'"
        >
          <span class="role">{{ m.role === "user" ? "顾客" : "助手" }}</span>
          <div class="bubble">{{ m.content }}</div>
        </div>
        <EmptyState v-if="messages.length === 0" title="暂无消息" />
      </div>
      <p class="readonly-hint">只读查看；接管回复请使用主聊天台。</p>
    </div>
  </div>
</template>

<style scoped>
.conversation-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px);
  max-width: 960px;
  margin: 0 auto;
}
.conv-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}
.back-btn {
  border: none;
  background: transparent;
  color: var(--el-color-primary, #409eff);
  cursor: pointer;
}
.conv-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.msg-row {
  margin-bottom: 12px;
}
.msg-row.user .bubble {
  background: #ecf5ff;
}
.msg-row.assistant .bubble {
  background: #f4f4f5;
}
.bubble {
  display: inline-block;
  padding: 8px 12px;
  border-radius: 8px;
  max-width: 80%;
}
.role {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.readonly-hint {
  padding: 12px 16px;
  font-size: 13px;
  color: #909399;
  border-top: 1px solid #ebeef5;
}
</style>
