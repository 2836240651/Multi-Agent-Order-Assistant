<script setup>
defineProps({
  size: {
    type: String,
    default: "24px",
  },
  color: {
    type: String,
    default: "#d95f3c",
  },
});
</script>

<template>
  <div class="spinner" :style="{ width: size, height: size }">
    <div class="spinner-ring" :style="{ borderColor: color }"></div>
  </div>
</template>

<style scoped>
.spinner {
  display: inline-block;
}

.spinner-ring {
  width: 100%;
  height: 100%;
  border: 3px solid rgba(0, 0, 0, 0.1);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
