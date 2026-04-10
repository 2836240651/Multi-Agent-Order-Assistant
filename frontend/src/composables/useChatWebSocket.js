import { ref, onUnmounted } from "vue";

export function useChatWebSocket() {
  const ws = ref(null);
  const isConnected = ref(false);
  const lastMessage = ref(null);
  const error = ref(null);
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECT_ATTEMPTS = 5;

  function connect(sessionId, userId, orderId) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/chat`;

    ws.value = new WebSocket(url);

    ws.value.onopen = () => {
      isConnected.value = true;
      error.value = null;
      reconnectAttempts = 0;
    };

    ws.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.error) {
          error.value = data.error;
        } else {
          lastMessage.value = data;
        }
      } catch (e) {
        error.value = "Failed to parse message";
      }
    };

    ws.value.onerror = () => {
      error.value = "WebSocket connection error";
      isConnected.value = false;
    };

    ws.value.onclose = () => {
      isConnected.value = false;
      ws.value = null;
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectTimer = setTimeout(() => {
          reconnectAttempts++;
          connect(sessionId, userId, orderId);
        }, 1000 * reconnectAttempts);
      }
    };
  }

  function send(message, sessionId, userId, orderId) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({
        message,
        session_id: sessionId,
        user_id: userId,
        order_id: orderId,
      }));
      return true;
    }
    return false;
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws.value) {
      ws.value.close();
      ws.value = null;
    }
    isConnected.value = false;
  }

  onUnmounted(() => {
    disconnect();
  });

  return {
    isConnected,
    lastMessage,
    error,
    connect,
    send,
    disconnect,
  };
}
