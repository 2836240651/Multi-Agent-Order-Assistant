<script setup>
/**
 * 坐席视图：会话收件箱。
 * 左侧会话列表 + 右侧消息流，支持选择会话查看历史。
 */
import { ref, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { api } from "../../api.js";

const router = useRouter();
import EmptyState from "../../components/EmptyState.vue";
import LoadingSpinner from "../../components/LoadingSpinner.vue";

const threads = ref([]);
const selectedThread = ref(null);
const messages = ref([]);
const loadingThreads = ref(false);
const loadingMessages = ref(false);
const messagesContainer = ref(null);

async function loadThreads() {
  loadingThreads.value = true;
  try {
    const resp = await api.listThreads();
    threads.value = resp.data.threads || [];
  } catch {
    threads.value = [];
  } finally {
    loadingThreads.value = false;
  }
}

async function selectThread(thread) {
  selectedThread.value = thread;
  loadingMessages.value = true;
  try {
    const resp = await api.getThreadMessages(thread.thread_id);
    messages.value = resp.data.messages || [];
    await nextTick();
    scrollToBottom();
  } catch {
    messages.value = [];
  } finally {
    loadingMessages.value = false;
  }
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

onMounted(loadThreads);
</script>

<template>
  <div class="session-inbox-page">
    <div class="inbox-sidebar">
      <div class="sidebar-header">
        <h3>会话收件箱</h3>
        <button class="btn-refresh" @click="loadThreads" title="刷新">⟳</button>
      </div>
      <LoadingSpinner v-if="loadingThreads" size="20px" />
      <EmptyState v-else-if="threads.length === 0" title="暂无会话" />
      <div v-else class="thread-list">
        <div
          v-for="t in threads"
          :key="t.thread_id"
          class="thread-item"
          :class="{ active: selectedThread?.thread_id === t.thread_id }"
          @click="router.push(`/agent/conversation/${t.thread_id}`)"
        >
          <div class="thread-id">{{ t.thread_id.slice(0, 8) }}...</div>
          <div class="thread-preview">{{ t.last_message }}</div>
          <div class="thread-time">{{ t.created_at?.slice(5, 16) }}</div>
        </div>
      </div>
    </div>

    <div class="inbox-main">
      <template v-if="selectedThread">
        <div class="chat-header">
          <span>会话 {{ selectedThread.thread_id.slice(0, 12) }}...</span>
        </div>
        <LoadingSpinner v-if="loadingMessages" size="24px" />
        <div v-else class="messages-area" ref="messagesContainer">
          <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
            <div class="msg-role">{{ m.role === "user" ? "客户" : m.role === "assistant" ? "AI" : "系统" }}</div>
            <div class="msg-content">{{ m.content }}</div>
            <div class="msg-time">{{ m.created_at?.slice(5, 16) }}</div>
          </div>
        </div>
      </template>
      <EmptyState v-else title="选择会话查看详情" description="从左侧列表中选择一个会话" />
    </div>
  </div>
</template>

<style scoped>
.session-inbox-page { display: flex; height: calc(100vh - 60px); }
.inbox-sidebar { width: 320px; border-right: 1px solid #eaecf0; display: flex; flex-direction: column; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #eaecf0; }
.sidebar-header h3 { margin: 0; font-size: 16px; }
.btn-refresh { background: none; border: none; font-size: 18px; cursor: pointer; color: #667085; }
.thread-list { flex: 1; overflow-y: auto; }
.thread-item { padding: 12px 16px; border-bottom: 1px solid #f2f4f7; cursor: pointer; }
.thread-item:hover { background: #f9fafb; }
.thread-item.active { background: #f4f0ff; border-left: 3px solid #7f56d9; }
.thread-id { font-size: 13px; font-weight: 600; color: #344054; }
.thread-preview { font-size: 13px; color: #667085; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.thread-time { font-size: 12px; color: #98a2b3; margin-top: 4px; }
.inbox-main { flex: 1; display: flex; flex-direction: column; }
.chat-header { padding: 12px 16px; border-bottom: 1px solid #eaecf0; font-weight: 600; }
.messages-area { flex: 1; overflow-y: auto; padding: 16px; }
.msg { margin-bottom: 12px; max-width: 70%; }
.msg.user { margin-left: auto; }
.msg.assistant { margin-right: auto; }
.msg-role { font-size: 12px; color: #667085; margin-bottom: 2px; }
.msg-content { padding: 8px 12px; border-radius: 8px; font-size: 14px; line-height: 1.5; }
.msg.user .msg-content { background: #7f56d9; color: #fff; border-bottom-right-radius: 2px; }
.msg.assistant .msg-content { background: #f2f4f7; color: #344054; border-bottom-left-radius: 2px; }
.msg.system .msg-content { background: #fef0c7; color: #b54708; font-size: 13px; }
.msg-time { font-size: 11px; color: #98a2b3; margin-top: 2px; }
</style>
