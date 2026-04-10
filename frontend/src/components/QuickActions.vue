<script setup>
defineProps({
  items: {
    type: Array,
    required: true,
  },
});

const emit = defineEmits(["click"]);

function handleClick(item) {
  emit("click", item);
}
</script>

<template>
  <div class="quick-actions">
    <button
      v-for="item in items"
      :key="item.key"
      class="quick-action-btn"
      @click="handleClick(item)"
    >
      <span class="action-icon">{{ item.icon }}</span>
      <span class="action-label">{{ item.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.quick-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.quick-action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  background: #fff;
  border: 1px solid #e8ecf0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 90px;
}

.quick-action-btn:hover {
  border-color: #d95f3c;
  background: #fff5f3;
  transform: translateY(-2px);
}

.action-icon {
  font-size: 24px;
}

.action-label {
  font-size: 13px;
  color: #305164;
  white-space: nowrap;
}
</style>
