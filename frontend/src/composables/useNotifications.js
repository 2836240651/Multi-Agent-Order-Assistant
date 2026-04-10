import { ref, onUnmounted } from "vue";

export function useNotifications() {
  const notifications = ref([]);
  const isConnected = ref(false);
  let ws = null;
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECT_ATTEMPTS = 5;
  const onNewNotification = ref(null);

  function connect(userId) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/notifications`;

    ws = new WebSocket(url);

    ws.onopen = () => {
      isConnected.value = true;
      reconnectAttempts = 0;
      ws.send(JSON.stringify({ user_id: userId }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "ticket_update") {
          notifications.value.unshift({
            id: Date.now(),
            ...data,
            timestamp: new Date().toISOString(),
            read: false,
          });
          if (onNewNotification.value) {
            onNewNotification.value(data);
          }
        }
      } catch (e) {
        console.error("Failed to parse notification:", e);
      }
    };

    ws.onerror = () => {
      isConnected.value = false;
    };

    ws.onclose = () => {
      isConnected.value = false;
      ws = null;
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS && userId) {
        reconnectTimer = setTimeout(() => {
          reconnectAttempts++;
          connect(userId);
        }, 2000 * reconnectAttempts);
      }
    };
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    isConnected.value = false;
  }

  function markAsRead(notificationId) {
    const notification = notifications.value.find((n) => n.id === notificationId);
    if (notification) {
      notification.read = true;
    }
  }

  function markAllAsRead() {
    notifications.value.forEach((n) => {
      n.read = true;
    });
  }

  function clearNotifications() {
    notifications.value = [];
  }

  onUnmounted(() => {
    disconnect();
  });

  return {
    notifications,
    isConnected,
    connect,
    disconnect,
    markAsRead,
    markAllAsRead,
    clearNotifications,
    onNewNotification,
  };
}
