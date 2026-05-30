<script setup>
/**
 * W1 ChatView：消费 /api/v1/chat SSE。事件类型见 设计.md §5.3。
 * - 流式渲染 token 到对话气泡
 * - citation 事件追加到右侧引用面板（卡片可点击展开父片）
 * - X-Tenant-Id 头从 localStorage 取（默认 tenant-a）
 */
import { reactive, ref, computed, onMounted, nextTick } from "vue";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const tenantId = ref(localStorage.getItem("tenant_id") || "tenant-a");
const threadId = ref("");
const input = ref("耳机能 7 天无理由退货吗？");
const sending = ref(false);
const messages = reactive([]); // {role, content, citations, agent_steps}
const citations = ref([]); // 最新一轮的引用列表（也存在 messages 内）
const activeCitation = ref(null); // 抽屉展开的 citation 对象

const chatBoxRef = ref(null);

function setTenant(value) {
  tenantId.value = value;
  localStorage.setItem("tenant_id", value);
}

async function scrollBottom() {
  await nextTick();
  if (chatBoxRef.value) chatBoxRef.value.scrollTop = chatBoxRef.value.scrollHeight;
}

async function send() {
  if (!input.value.trim() || sending.value) return;
  const userMsg = { role: "user", content: input.value.trim(), citations: [], agent_steps: [] };
  messages.push(userMsg);
  const asstMsg = reactive({ role: "assistant", content: "", citations: [], agent_steps: [] });
  messages.push(asstMsg);
  input.value = "";
  sending.value = true;
  scrollBottom();

  try {
    const resp = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Id": tenantId.value,
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        messages: messages
          .filter((m) => m !== asstMsg)
          .map((m) => ({ role: m.role, content: m.content })),
        thread_id: threadId.value || undefined,
        version: "v3",
      }),
    });

    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => "");
      asstMsg.content = `请求失败：${resp.status} ${text}`;
      sending.value = false;
      return;
    }

    threadId.value = resp.headers.get("X-Thread-Id") || threadId.value;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // 切分 \n\n 分隔的 SSE 帧
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const lines = frame.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        let payload;
        try {
          payload = JSON.parse(data);
        } catch (e) {
          payload = { raw: data };
        }
        handleEvent(asstMsg, event, payload);
        scrollBottom();
      }
    }
  } catch (err) {
    asstMsg.content += `\n[网络错误] ${err.message || err}`;
  } finally {
    sending.value = false;
  }
}

function handleEvent(asstMsg, event, payload) {
  switch (event) {
    case "start":
      asstMsg.agent_steps.push({ agent: "start", payload });
      break;
    case "agent_step":
      asstMsg.agent_steps.push(payload);
      break;
    case "citation":
      asstMsg.citations.push(payload);
      citations.value = asstMsg.citations;
      break;
    case "token":
      asstMsg.content += payload.text || "";
      break;
    case "no_match":
      asstMsg.content += payload.text || "未在政策中找到相关规定。";
      break;
    case "done":
      asstMsg.done = true;
      break;
    case "error":
      asstMsg.content += `\n[错误] ${payload.message || ""}`;
      break;
    default:
      break;
  }
}

function openCitation(c) {
  activeCitation.value = c;
}

const tenantOptions = [
  { value: "tenant-a", label: "Tenant A" },
  { value: "tenant-b", label: "Tenant B" },
];

onMounted(() => scrollBottom());
</script>

<template>
  <div class="chat-layout">
    <header class="chat-header">
      <h2>RetailGuard 售后助手</h2>
      <div class="tenant-picker">
        <label>租户：</label>
        <select :value="tenantId" @change="(e) => setTenant(e.target.value)">
          <option v-for="t in tenantOptions" :key="t.value" :value="t.value">
            {{ t.label }}
          </option>
        </select>
        <span class="thread-id" v-if="threadId">thread: {{ threadId.slice(0, 8) }}</span>
      </div>
    </header>

    <div class="chat-body">
      <section class="chat-box" ref="chatBoxRef">
        <div v-if="messages.length === 0" class="empty-tip">
          试试问："7 天无理由怎么算？" 或 "积分多久过期？"
        </div>
        <div
          v-for="(m, idx) in messages"
          :key="idx"
          :class="['msg', m.role]"
        >
          <div class="bubble">
            <pre class="content">{{ m.content || (m.role === 'assistant' ? '思考中…' : '') }}</pre>
            <div v-if="m.citations && m.citations.length" class="cite-inline">
              <span class="cite-label">引用：</span>
              <button
                v-for="c in m.citations"
                :key="c.id"
                class="cite-chip"
                @click="openCitation(c)"
              >
                {{ c.id.replace('cit_', '[') + ']' }} {{ c.doc_no }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <aside class="cite-panel">
        <h3>引用片段 ({{ citations.length }})</h3>
        <div v-if="!citations.length" class="empty-tip">尚无引用</div>
        <article
          v-for="c in citations"
          :key="c.id"
          class="cite-card"
          @click="openCitation(c)"
        >
          <div class="cite-card-title">{{ c.title }}</div>
          <div class="cite-card-meta">{{ c.doc_no }}</div>
          <div class="cite-card-snippet">{{ c.snippet }}</div>
        </article>
      </aside>
    </div>

    <footer class="chat-input">
      <textarea
        v-model="input"
        rows="2"
        placeholder="输入问题，回车发送（Shift+回车换行）"
        @keydown.enter.exact.prevent="send"
        :disabled="sending"
      />
      <button class="send-btn" :disabled="sending || !input.trim()" @click="send">
        {{ sending ? '生成中…' : '发送' }}
      </button>
    </footer>

    <div v-if="activeCitation" class="cite-drawer" @click.self="activeCitation = null">
      <div class="cite-drawer-panel">
        <header>
          <strong>{{ activeCitation.title }}</strong>
          <button class="close-btn" @click="activeCitation = null">×</button>
        </header>
        <div class="meta">{{ activeCitation.doc_no }} · chunk {{ activeCitation.chunk_id }}</div>
        <pre class="full-text">{{ activeCitation.snippet }}</pre>
        <p class="hint">完整父片需调用 /api/v1/kb/chunks/{id}（W2 接入）。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f6f7fa;
}
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e6e8eb;
}
.tenant-picker {
  font-size: 13px;
  color: #5f6368;
}
.tenant-picker select {
  margin: 0 12px 0 4px;
  padding: 4px 8px;
}
.thread-id {
  margin-left: 8px;
  color: #9aa0a6;
  font-family: monospace;
}
.chat-body {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  padding: 16px 24px;
  overflow: hidden;
}
.chat-box {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.msg {
  display: flex;
}
.msg.user {
  justify-content: flex-end;
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  background: #eef1f6;
}
.msg.user .bubble {
  background: #4f7cff;
  color: #fff;
}
.bubble .content {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  margin: 0;
}
.cite-inline {
  margin-top: 8px;
  font-size: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.cite-label {
  color: #5f6368;
}
.cite-chip {
  background: #fff;
  border: 1px solid #c9d5ff;
  color: #2c54d8;
  padding: 2px 8px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 12px;
}
.cite-chip:hover {
  background: #eef2ff;
}
.cite-panel {
  background: #fff;
  border-radius: 10px;
  padding: 12px;
  overflow-y: auto;
}
.cite-panel h3 {
  font-size: 14px;
  margin: 0 0 8px;
}
.cite-card {
  border: 1px solid #e6e8eb;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
  cursor: pointer;
}
.cite-card:hover {
  border-color: #4f7cff;
}
.cite-card-title {
  font-weight: 600;
  font-size: 13px;
}
.cite-card-meta {
  font-size: 11px;
  color: #9aa0a6;
  margin: 2px 0 6px;
}
.cite-card-snippet {
  font-size: 12px;
  color: #3c4043;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.chat-input {
  display: flex;
  gap: 8px;
  padding: 12px 24px;
  background: #fff;
  border-top: 1px solid #e6e8eb;
}
.chat-input textarea {
  flex: 1;
  resize: none;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-family: inherit;
}
.send-btn {
  padding: 0 20px;
  background: #4f7cff;
  color: #fff;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
}
.send-btn:disabled {
  background: #9aa0a6;
  cursor: not-allowed;
}
.empty-tip {
  color: #9aa0a6;
  font-size: 13px;
  text-align: center;
  padding: 24px;
}
.cite-drawer {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  justify-content: flex-end;
  z-index: 99;
}
.cite-drawer-panel {
  width: 480px;
  max-width: 100%;
  background: #fff;
  padding: 16px 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cite-drawer-panel header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.close-btn {
  background: none;
  border: 0;
  font-size: 22px;
  cursor: pointer;
  color: #5f6368;
}
.full-text {
  background: #f6f7fa;
  padding: 10px;
  border-radius: 6px;
  white-space: pre-wrap;
}
.hint {
  font-size: 12px;
  color: #9aa0a6;
}
</style>
