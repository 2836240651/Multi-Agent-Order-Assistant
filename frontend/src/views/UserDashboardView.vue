<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { useToast } from "../composables/useToast";
import { useChatWebSocket } from "../composables/useChatWebSocket";
import { useNotifications } from "../composables/useNotifications";

const router = useRouter();
const toast = useToast();
const { isConnected, lastMessage, error: wsError, connect, send, disconnect } = useChatWebSocket();
const { notifications, connect: connectNotifications, onNewNotification } = useNotifications();

const user = ref(null);
const orders = ref([]);
const tickets = ref([]);
const chatMessages = ref([]);
const selectedOrder = ref(null);
const activeTicketId = ref("");
const chatSessionId = ref("");
const activeTab = ref("orders");
const isLoading = reactive({
  page: true,
  chat: false,
  tickets: false
});
const showLogoutModal = ref(false);

watch(lastMessage, (msg) => {
  if (msg) {
    chatMessages.value.push({
      role: "assistant",
      content: msg.response,
      created_at: new Date().toISOString(),
      action: msg.action,
      execution_status: msg.execution_status,
      execution_status_label: msg.execution_status_label,
      ticket_id: msg.ticket_id,
      ticket_status: msg.ticket_status,
      ticket_status_label: msg.ticket_status_label,
      next_step: msg.next_step
    });
    loadDashboard();
    loadChatHistory(selectedOrder.value?.order_id);
    isLoading.chat = false;
  }
});

watch(wsError, (err) => {
  if (err) {
    toast.error(`连接错误：${err}`);
    isLoading.chat = false;
  }
});

const chatForm = reactive({
  message: "",
  user_id: ""
});

const orderStatusMap = {
  pending: { label: "待处理", tone: "warning" },
  processing: { label: "处理中", tone: "info" },
  shipped: { label: "已发货", tone: "info" },
  delivered: { label: "已送达", tone: "success" },
  refunded: { label: "已退款", tone: "muted" },
  cancelled: { label: "已取消", tone: "danger" },
  refund_requested: { label: "退款审核中", tone: "warning" },
  address_updated: { label: "地址已更新", tone: "success" }
};

const ticketStatusMap = {
  created: { label: "已创建", tone: "muted" },
  pending: { label: "待处理", tone: "warning" },
  pending_user_confirm: { label: "待补充信息", tone: "warning" },
  pending_manual_review: { label: "待人工审核", tone: "danger" },
  pending_review: { label: "待业务审核", tone: "warning" },
  in_progress: { label: "处理中", tone: "info" },
  resolved: { label: "已解决", tone: "success" },
  rejected: { label: "已拒绝", tone: "danger" },
  closed: { label: "已关闭", tone: "muted" }
};

const executionStatusMap = {
  executed: "已执行",
  submitted: "已提交",
  waiting_user_input: "待补充信息",
  waiting_manual_review: "待人工审核",
  failed: "执行失败",
  degraded_fallback: "降级兜底"
};

const userId = computed(() => user.value?.user_id || chatForm.user_id || localStorage.getItem("user_id") || "");
const selectedOrderTickets = computed(() =>
  selectedOrder.value ? tickets.value.filter((ticket) => ticket.order_id === selectedOrder.value.order_id) : []
);
const activeTicket = computed(() => {
  if (!selectedOrderTickets.value.length) {
    return null;
  }
  return (
    selectedOrderTickets.value.find((ticket) => ticket.ticket_id === activeTicketId.value) ||
    selectedOrderTickets.value[0]
  );
});
const openTicketCount = computed(() =>
  tickets.value.filter((ticket) => !["resolved", "rejected", "closed"].includes(ticket.ticket_status || ticket.status)).length
);
const reviewTicketCount = computed(() =>
  tickets.value.filter((ticket) =>
    ["pending_review", "pending_manual_review"].includes(ticket.ticket_status || ticket.status)
  ).length
);

onMounted(async () => {
  const storedUser = localStorage.getItem("user");
  if (!storedUser) {
    router.push("/login");
    return;
  }

  user.value = JSON.parse(storedUser);
  chatForm.user_id = user.value.user_id;
  await loadDashboard();

  connectNotifications(user.value.user_id);
  onNewNotification.value = (notification) => {
    toast.info(notification.message);
    loadDashboard();
  };
});

onUnmounted(() => {
  disconnect();
});

async function loadDashboard() {
  isLoading.page = true;
  try {
    const result = await api.user(userId.value);
    user.value = result.user;
    orders.value = result.orders || [];
    await loadTickets();
    if (selectedOrder.value) {
      const latestSelected = orders.value.find((order) => order.order_id === selectedOrder.value.order_id);
      if (latestSelected) {
        selectedOrder.value = latestSelected;
      }
    }
  } catch (error) {
    toast.error(`加载用户数据失败：${error.message}`);
  } finally {
    isLoading.page = false;
  }
}

async function loadTickets() {
  if (!userId.value) {
    tickets.value = [];
    return;
  }
  isLoading.tickets = true;
  try {
    const result = await api.tickets({
      user_id: userId.value,
      include_closed: true,
      limit: 100
    });
    tickets.value = result.items || [];
    if (selectedOrder.value) {
      const nextTicket = tickets.value.find((ticket) => ticket.order_id === selectedOrder.value.order_id);
      activeTicketId.value = nextTicket?.ticket_id || "";
    }
  } catch (error) {
    toast.error(`加载工单失败：${error.message}`);
  } finally {
    isLoading.tickets = false;
  }
}

async function loadChatHistory(orderId) {
  if (!orderId || !userId.value) {
    chatMessages.value = [];
    return;
  }
  try {
    const result = await api.chatHistory(userId.value, orderId);
    chatMessages.value = result.items || [];
  } catch (error) {
    toast.error(`加载聊天记录失败：${error.message}`);
    chatMessages.value = [];
  }
}

async function selectOrder(order) {
  selectedOrder.value = order;
  chatSessionId.value = `user_${userId.value}_${order.order_id}`;
  chatForm.message = "";
  await loadChatHistory(order.order_id);
  const matchingTicket = tickets.value.find((ticket) => ticket.order_id === order.order_id);
  activeTicketId.value = matchingTicket?.ticket_id || "";
  connect(chatSessionId.value, userId.value, order.order_id);
}

async function submitChat() {
  if (!selectedOrder.value) {
    toast.warning("请先选择一个订单");
    return;
  }
  if (!chatForm.message.trim()) {
    toast.warning("请输入消息内容");
    return;
  }

  const outgoing = chatForm.message.trim();
  chatForm.message = "";
  chatMessages.value.push({
    role: "user",
    content: outgoing,
    created_at: new Date().toISOString()
  });

  isLoading.chat = true;
  if (isConnected.value) {
    send(outgoing, chatSessionId.value, userId.value, selectedOrder.value.order_id);
  } else {
    try {
      const result = await api.chat({
        message: outgoing,
        user_id: userId.value,
        session_id: chatSessionId.value,
        order_id: selectedOrder.value.order_id
      });

      chatMessages.value.push({
        role: "assistant",
        content: result.response,
        created_at: new Date().toISOString(),
        action: result.action,
        execution_status: result.execution_status,
        execution_status_label: result.execution_status_label,
        ticket_id: result.ticket_id,
        ticket_status: result.ticket_status,
        ticket_status_label: result.ticket_status_label,
        next_step: result.next_step
      });

      await Promise.all([loadDashboard(), loadChatHistory(selectedOrder.value.order_id)]);
    } catch (error) {
      toast.error(`发送失败：${error.message}`);
    } finally {
      isLoading.chat = false;
    }
  }
}

async function closeTicket(ticket) {
  try {
    await api.transitionTicket(
      ticket.ticket_id,
      {
        status: "closed",
        note: "Closed by customer from user dashboard."
      },
      userId.value
    );
    toast.success("工单已关闭");
    await loadTickets();
  } catch (error) {
    toast.error(`关闭工单失败：${error.message}`);
  }
}

async function focusTicket(ticket) {
  const targetOrder = orders.value.find((order) => order.order_id === ticket.order_id);
  if (targetOrder) {
    await selectOrder(targetOrder);
  }
  activeTicketId.value = ticket.ticket_id;
}

function handleLogout() {
  showLogoutModal.value = true;
}

function confirmLogout() {
  localStorage.removeItem("user");
  localStorage.removeItem("user_id");
  showLogoutModal.value = false;
  router.push("/login");
}

function formatAmount(amount) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY"
  }).format(Number(amount || 0));
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function formatShortDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.split(" ")[0] || value;
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function orderStatusInfo(status) {
  return orderStatusMap[status] || { label: status || "未知", tone: "muted" };
}

function ticketStatusInfo(status) {
  return ticketStatusMap[status] || { label: status || "未知", tone: "muted" };
}

function executionStatusLabel(status) {
  return executionStatusMap[status] || status || "";
}

function canCloseTicket(ticket) {
  const allowed = ticket.allowed_transitions || [];
  return allowed.includes("closed") && ["resolved", "rejected"].includes(ticket.ticket_status || ticket.status);
}

function ticketTimeline(ticket) {
  const history = [...(ticket?.history || [])];
  return history.reverse();
}

function latestTicketSummary(ticket) {
  if (!ticket?.history?.length) {
    return ticket?.ticket_next_step || "等待系统推进";
  }
  return ticket.history[ticket.history.length - 1]?.note || ticket.ticket_next_step || "等待系统推进";
}
</script>

<template>
  <div class="user-dashboard">
    <header class="dashboard-header">
      <div class="header-left">
        <h1>零售守护者</h1>
      </div>
      <div class="header-right">
        <div class="notification-bell" @click="activeTab = 'notifications'">
          <span class="bell-icon">🔔</span>
          <span v-if="notifications.filter(n => !n.read).length > 0" class="notification-badge">
            {{ notifications.filter(n => !n.read).length }}
          </span>
        </div>
        <span class="user-name">{{ user?.username || "用户" }}</span>
        <button class="logout-btn" @click="showLogoutModal = true">退出</button>
      </div>
    </header>

    <div class="tab-nav">
      <button 
        class="tab-btn" 
        :class="{ active: activeTab === 'orders' }"
        @click="activeTab = 'orders'"
      >
        📦 我的订单
      </button>
      <button 
        class="tab-btn" 
        :class="{ active: activeTab === 'tickets' }"
        @click="activeTab = 'tickets'"
      >
        🎫 我的工单
      </button>
      <button 
        class="tab-btn" 
        :class="{ active: activeTab === 'notifications' }"
        @click="activeTab = 'notifications'"
      >
        🔔 通知 {{ notifications.filter(n => !n.read).length > 0 ? `(${notifications.filter(n => !n.read).length})` : '' }}
      </button>
    </div>

    <div class="dashboard-content" v-if="activeTab === 'notifications'">
      <section class="panel notifications-panel">
        <div class="section-head">
          <h2>通知中心</h2>
          <button v-if="notifications.length > 0" class="ghost-button" @click="notifications = []">清空</button>
        </div>

        <div v-if="notifications.length === 0" class="empty-state">暂无通知</div>
        <div v-else class="notification-list">
          <div
            v-for="notification in notifications"
            :key="notification.id"
            class="notification-item"
            :class="{ unread: !notification.read }"
            @click="notification.read = true"
          >
            <div class="notification-icon">{{ notification.type === 'ticket_update' ? '🎫' : '💬' }}</div>
            <div class="notification-content">
              <p class="notification-message">{{ notification.message }}</p>
              <span class="notification-time">{{ formatDateTime(notification.timestamp) }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>

    <div class="dashboard-content" v-if="activeTab === 'orders'">
      <section class="panel orders-panel">
        <div class="section-head">
          <h2>我的订单</h2>
          <span class="subtle-text">{{ isLoading.page ? "加载中" : `${orders.length} 个订单` }}</span>
        </div>

        <div v-if="isLoading.page" class="loading-state">正在加载订单...</div>
        <div v-else-if="orders.length === 0" class="empty-state">暂无订单</div>
        <div v-else class="order-list">
          <button
            v-for="order in orders"
            :key="order.order_id"
            class="order-card"
            :class="{ active: selectedOrder?.order_id === order.order_id }"
            @click="selectOrder(order)"
          >
            <div class="order-card-head">
              <span class="order-id">{{ order.order_id }}</span>
              <span class="status-pill" :class="orderStatusInfo(order.status).tone">
                {{ orderStatusInfo(order.status).label }}
              </span>
            </div>
            <h3>{{ order.product_name }}</h3>
            <p>{{ formatShortDate(order.order_date) }}</p>
            <div class="order-card-foot">
              <span>{{ formatAmount(order.amount) }}</span>
              <span>{{ order.address || "暂无地址" }}</span>
            </div>
          </button>
        </div>
      </section>

      <section v-if="selectedOrder" class="panel detail-panel">
        <div class="section-head">
          <div>
            <h2>{{ selectedOrder.product_name }}</h2>
            <p class="subtle-text">{{ selectedOrder.order_id }}</p>
          </div>
          <span class="status-pill" :class="orderStatusInfo(selectedOrder.status).tone">
            {{ orderStatusInfo(selectedOrder.status).label }}
          </span>
        </div>

        <div class="order-summary">
          <div>
            <span class="summary-label">订单金额</span>
            <strong>{{ formatAmount(selectedOrder.amount) }}</strong>
          </div>
          <div>
            <span class="summary-label">下单时间</span>
            <strong>{{ formatShortDate(selectedOrder.order_date) }}</strong>
          </div>
          <div>
            <span class="summary-label">收货地址</span>
            <strong>{{ selectedOrder.address || "暂无地址" }}</strong>
          </div>
        </div>

        <section class="embedded-panel chat-panel">
          <div class="section-head">
            <h3>订单对话</h3>
            <span class="subtle-text">上下文已绑定当前订单</span>
          </div>

          <div class="chat-stream">
            <div v-if="chatMessages.length === 0" class="empty-inline">还没有聊天记录</div>

            <div
              v-for="(message, index) in chatMessages"
              :key="`${message.role}-${index}-${message.created_at}`"
              class="message-row"
              :class="message.role"
            >
              <div class="message-avatar">{{ message.role === "user" ? "你" : "AI" }}</div>
              <div class="message-bubble">
                <p class="message-text">{{ message.content }}</p>
                <span class="message-time">{{ formatDateTime(message.created_at) }}</span>
              </div>
            </div>
          </div>

          <div class="chat-input">
            <input
              v-model="chatForm.message"
              type="text"
              placeholder="输入您的问题..."
              @keyup.enter="submitChat"
            />
            <button class="primary-btn" :disabled="isLoading.chat" @click="submitChat">
              {{ isLoading.chat ? "发送中..." : "发送" }}
            </button>
          </div>
        </section>
      </section>

      <section v-else class="panel empty-detail">
        <div class="empty-state">请选择一个订单查看详情</div>
      </section>
    </div>

    <div class="dashboard-content" v-if="activeTab === 'tickets'">
      <section class="panel tickets-panel">
        <div class="section-head">
          <h2>我的工单</h2>
          <span class="subtle-text">{{ isLoading.tickets ? "加载中" : `${tickets.length} 个工单` }}</span>
        </div>

        <div v-if="isLoading.tickets" class="loading-state">正在加载工单...</div>
        <div v-else-if="tickets.length === 0" class="empty-state">暂无工单记录</div>
        <div v-else class="ticket-list">
          <button
            v-for="ticket in tickets"
            :key="ticket.ticket_id"
            class="ticket-card"
            :class="{ active: activeTicketId === ticket.ticket_id }"
            @click="focusTicket(ticket)"
          >
            <div class="ticket-card-head">
              <span class="ticket-id">{{ ticket.ticket_id }}</span>
              <span class="status-pill" :class="ticketStatusInfo(ticket.ticket_status || ticket.status).tone">
                {{ ticket.ticket_status_label || ticketStatusInfo(ticket.ticket_status || ticket.status).label }}
              </span>
            </div>
            <h3>{{ ticket.title }}</h3>
            <p class="ticket-meta">{{ ticket.order_id || "无关联订单" }}</p>
            <p class="ticket-time">创建于 {{ formatDateTime(ticket.created_at) }}</p>
          </button>
        </div>
      </section>

      <section v-if="activeTicketId" class="panel ticket-detail-panel">
        <div class="section-head">
          <h2>工单详情</h2>
        </div>
        
        <div class="ticket-detail-info">
          <div class="detail-row">
            <span class="detail-label">工单号</span>
            <span class="detail-value">{{ activeTicket?.ticket_id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">状态</span>
            <span class="status-pill" :class="ticketStatusInfo(activeTicket?.ticket_status || activeTicket?.status).tone">
              {{ activeTicket?.ticket_status_label || ticketStatusInfo(activeTicket?.ticket_status || activeTicket?.status).label }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">关联订单</span>
            <span class="detail-value">{{ activeTicket?.order_id || "无" }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">创建时间</span>
            <span class="detail-value">{{ formatDateTime(activeTicket?.created_at) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">描述</span>
            <span class="detail-value">{{ activeTicket?.description }}</span>
          </div>
          <div v-if="activeTicket?.ticket_next_step" class="detail-row next-step-row">
            <span class="detail-label">待处理事项</span>
            <span class="detail-value next-step-value">{{ activeTicket?.ticket_next_step }}</span>
          </div>
        </div>
      </section>
    </div>

    <div v-if="showLogoutModal" class="modal-overlay" @click.self="showLogoutModal = false">
      <div class="modal-card">
        <h3>确认退出</h3>
        <p>退出后将返回登录页。</p>
        <div class="modal-actions">
          <button class="secondary-btn" @click="showLogoutModal = false">取消</button>
          <button class="primary-btn danger" @click="confirmLogout">退出登录</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.user-dashboard {
  min-height: 100vh;
  background: #f5f5f5;
  color: #333;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #eee;
}

.header-left h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #e74c3c;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-name {
  font-size: 14px;
  color: #666;
}

.logout-btn {
  padding: 6px 16px;
  background: #f5f5f5;
  border: 1px solid #ddd;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #666;
}

.logout-btn:hover {
  background: #eee;
}

.tab-nav {
  display: flex;
  gap: 0;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #eee;
}

.tab-btn {
  padding: 12px 24px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: #e74c3c;
}

.tab-btn.active {
  color: #e74c3c;
  border-bottom-color: #e74c3c;
  font-weight: 500;
}

.dashboard-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.panel {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  padding: 16px;
}

.empty-detail {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.profile-card {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  background: #e74c3c;
}

.profile-card h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.profile-card p {
  margin: 4px 0 0;
  color: #999;
  font-size: 13px;
}

.vip-chip {
  display: inline-flex;
  align-items: center;
  margin-top: 6px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #fff3e0;
  color: #e65100;
  font-size: 12px;
}

.stats-card {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.stat-item {
  text-align: center;
  padding: 8px 4px;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #e74c3c;
}

.stat-label {
  font-size: 12px;
  color: #999;
}

.ticket-overview h3 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #666;
}

.ticket-list-item {
  display: block;
  width: 100%;
  text-align: left;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.ticket-list-item:hover {
  background: #fff;
  border-color: #e74c3c;
  box-shadow: 0 2px 8px rgba(231,76,60,0.1);
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-content: start;
}

.panel {
  padding: 16px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.subtle-text {
  color: #999;
  font-size: 13px;
}

.order-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.order-card {
  text-align: left;
  width: 100%;
  border: 1px solid #eee;
  background: #fafafa;
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.order-card:hover {
  background: #fff;
  border-color: #e74c3c;
  box-shadow: 0 2px 8px rgba(231,76,60,0.1);
}

.order-card.active {
  background: #fff;
  border-color: #e74c3c;
  box-shadow: 0 2px 8px rgba(231,76,60,0.15);
}

.order-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.order-id {
  font-size: 12px;
  color: #999;
}

.order-card h3 {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 500;
}

.order-card > p {
  margin: 0;
  font-size: 12px;
  color: #999;
}

.order-card-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #eee;
  font-size: 13px;
}

.order-card-foot span:first-child {
  font-weight: 700;
  color: #e74c3c;
}

.ticket-card {
  display: block;
  width: 100%;
  text-align: left;
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.ticket-card:hover {
  background: #fff;
  border-color: #e74c3c;
  box-shadow: 0 2px 8px rgba(231,76,60,0.1);
}

.ticket-card.active {
  background: #fff;
  border-color: #e74c3c;
  box-shadow: 0 2px 8px rgba(231,76,60,0.15);
}

.ticket-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.ticket-card h3 {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 500;
}

.ticket-meta {
  margin: 0 0 4px;
  font-size: 12px;
  color: #666;
}

.ticket-time {
  margin: 0;
  font-size: 11px;
  color: #999;
}

.ticket-detail-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.detail-label {
  width: 80px;
  font-size: 13px;
  color: #999;
  flex-shrink: 0;
}

.detail-value {
  font-size: 13px;
  color: #333;
}

.next-step-row {
  background: #fff3e0;
  padding: 10px 12px;
  border-radius: 6px;
  margin-top: 8px;
}

.next-step-value {
  color: #e65100;
  font-weight: 500;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-pill.success {
  background: #e8f5e9;
  color: #2e7d32;
}

.status-pill.info {
  background: #e3f2fd;
  color: #1565c0;
}

.status-pill.warning {
  background: #fff3e0;
  color: #ef6c00;
}

.status-pill.danger {
  background: #ffebee;
  color: #c62828;
}

.status-pill.muted {
  background: #f5f5f5;
  color: #757575;
}

.detail-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.order-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}

.order-summary > div {
  text-align: center;
}

.order-summary .summary-label {
  display: block;
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.order-summary strong {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.summary-label {
  display: block;
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.summary-value {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.embedded-panel {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 12px;
}

.ticket-detail {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #eee;
}

.ticket-detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.ticket-detail h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.timeline-item {
  display: flex;
  gap: 12px;
  position: relative;
  padding-left: 20px;
  padding-bottom: 16px;
}

.timeline-item::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e74c3c;
}

.timeline-item::after {
  content: '';
  position: absolute;
  left: 8px;
  top: 16px;
  width: 2px;
  height: calc(100% - 16px);
  background: #eee;
}

.timeline-item:last-child::after {
  display: none;
}

.timeline-content {
  flex: 1;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 2px;
}

.timeline-time {
  color: #999;
  font-size: 12px;
}

.chat-panel {
  grid-column: span 2;
}

.chat-stream {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 200px;
  max-height: 320px;
  overflow-y: auto;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}

.message-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: #e74c3c;
}

.message-row.user .message-avatar {
  background: #666;
}

.message-bubble {
  max-width: 70%;
  border-radius: 8px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #eee;
  font-size: 14px;
  line-height: 1.5;
}

.message-row.user .message-bubble {
  background: #e74c3c;
  color: #fff;
  border-color: #e74c3c;
}

.message-text {
  margin: 0;
  white-space: pre-wrap;
}

.message-meta {
  margin-top: 4px;
  font-size: 11px;
  color: #999;
}

.message-time {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #999;
}

.chat-input {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.chat-input input {
  flex: 1;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.chat-input input:focus {
  border-color: #e74c3c;
}

.primary-btn,
.secondary-btn,
.logout-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  padding: 10px 16px;
  transition: all 0.2s;
  border: none;
}

.primary-btn {
  color: #fff;
  background: #e74c3c;
}

.primary-btn:hover {
  background: #c0392b;
}

.primary-btn.danger {
  background: #e74c3c;
}

.secondary-btn,
.logout-btn {
  color: #666;
  background: #f5f5f5;
  border: 1px solid #ddd;
}

.secondary-btn:hover,
.logout-btn:hover {
  background: #eee;
}

.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-state,
.empty-state,
.empty-inline {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #999;
  font-size: 14px;
}

.empty-state {
  min-height: 160px;
  border-radius: 6px;
  border: 1px dashed #ddd;
  background: #fafafa;
}

.empty-inline {
  padding: 16px;
  border: 1px dashed #ddd;
  border-radius: 6px;
  background: #fafafa;
  font-size: 13px;
}

.ticket-list-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.ticket-id {
  font-size: 12px;
  color: #999;
}

.ticket-list-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 500;
}

.ticket-list-meta {
  margin: 0;
  font-size: 12px;
  color: #999;
}

.ticket-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.order-ticket-card {
  display: block;
  width: 100%;
  text-align: left;
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.order-ticket-card:hover {
  background: #fff;
  border-color: #e74c3c;
}

.order-ticket-card.active {
  background: #fff;
  border-color: #e74c3c;
  box-shadow: 0 2px 8px rgba(231,76,60,0.1);
}

.order-ticket-card h4 {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 500;
}

.order-ticket-card p {
  margin: 0;
  font-size: 12px;
  color: #666;
}

.order-ticket-card small {
  font-size: 11px;
  color: #999;
}

.summary-value {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.summary-address {
  text-align: center;
}

.summary-address .summary-value {
  font-size: 13px;
}

.empty-state.large {
  min-height: 200px;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.modal-card {
  width: 320px;
  border-radius: 8px;
  background: #fff;
  padding: 24px;
}

.modal-card h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.modal-card p {
  margin: 12px 0 0;
  color: #666;
  font-size: 14px;
}

.modal-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.modal-actions button {
  flex: 1;
}

@media (max-width: 1024px) {
  .dashboard-shell {
    grid-template-columns: 1fr;
  }
  
  .content-grid {
    grid-template-columns: 1fr;
  }
  
  .chat-panel {
    grid-column: span 1;
  }
  
  .sidebar {
    position: static;
  }
}

@media (max-width: 640px) {
  .dashboard-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .dashboard-shell {
    padding: 12px;
  }
  
  .order-summary {
    grid-template-columns: 1fr;
  }
}

.notification-bell {
  position: relative;
  cursor: pointer;
  padding: 4px 8px;
}

.notification-bell .bell-icon {
  font-size: 18px;
}

.notification-badge {
  position: absolute;
  top: -2px;
  right: 0;
  background: #e74c3c;
  color: #fff;
  font-size: 10px;
  padding: 2px 5px;
  border-radius: 10px;
  min-width: 16px;
  text-align: center;
}

.notification-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.notification-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: #f9f9f9;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.notification-item:hover {
  background: #f0f0f0;
}

.notification-item.unread {
  background: #fff;
  border-left: 3px solid #e74c3c;
}

.notification-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.notification-content {
  flex: 1;
}

.notification-message {
  margin: 0 0 4px 0;
  font-size: 14px;
  color: #333;
}

.notification-time {
  font-size: 12px;
  color: #999;
}
</style>
