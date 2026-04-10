import { ref } from "vue";

const toasts = ref([]);
let toastId = 0;

export function useToast() {
  function addToast({ type = "info", title, message, duration = 4000 }) {
    const id = ++toastId;
    toasts.value.push({ id, type, title, message });

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }

    return id;
  }

  function removeToast(id) {
    const index = toasts.value.findIndex((t) => t.id === id);
    if (index > -1) {
      toasts.value.splice(index, 1);
    }
  }

  function success(message, title = "成功") {
    return addToast({ type: "success", title, message });
  }

  function error(message, title = "错误") {
    return addToast({ type: "error", title, message, duration: 6000 });
  }

  function warning(message, title = "警告") {
    return addToast({ type: "warning", title, message });
  }

  function info(message, title = "提示") {
    return addToast({ type: "info", title, message });
  }

  return {
    toasts,
    addToast,
    removeToast,
    success,
    error,
    warning,
    info,
  };
}
