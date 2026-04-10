<script setup>
defineProps({
  icon: {
    type: String,
    default: "📭",
  },
  title: {
    type: String,
    default: "暂无数据",
  },
  description: {
    type: String,
    default: "",
  },
});
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon">{{ icon }}</div>
    <div class="empty-title">{{ title }}</div>
    <div v-if="description" class="empty-desc">{{ description }}</div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.8;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #14313d;
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 14px;
  color: #627983;
  max-width: 300px;
}
</style>
