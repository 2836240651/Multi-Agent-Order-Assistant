<script setup>
/**
 * 管理员视图：灰度版本管理（滑块调整权重 + 实时预览 + 审计日志）。
 */
import { ref, onMounted, computed } from "vue";
import { api } from "../../api.js";

const weights = ref({ v1: 0, v2: 0, v3: 100 });
const auditLog = ref([]);
const saving = ref(false);
const lastSaved = ref("");

const total = computed(() => weights.value.v1 + weights.value.v2 + weights.value.v3);

function normalize() {
  const t = total.value;
  if (t === 0) return;
  weights.value.v1 = Math.round((weights.value.v1 / t) * 100);
  weights.value.v2 = Math.round((weights.value.v2 / t) * 100);
  weights.value.v3 = 100 - weights.value.v1 - weights.value.v2;
}

async function load() {
  try {
    const resp = await api.getRollout();
    const w = resp.data.weights;
    weights.value = {
      v1: Math.round((w.v1 || 0) * 100),
      v2: Math.round((w.v2 || 0) * 100),
      v3: Math.round((w.v3 || 0) * 100),
    };
  } catch {}

  try {
    const resp = await api.rolloutAudit(10);
    auditLog.value = resp.data.entries || [];
  } catch {}
}

async function save() {
  saving.value = true;
  try {
    normalize();
    await api.updateRollout({
      v1: weights.value.v1 / 100,
      v2: weights.value.v2 / 100,
      v3: weights.value.v3 / 100,
    });
    lastSaved.value = new Date().toLocaleTimeString();
    await load();
  } catch (e) {
    alert("保存失败: " + e.message);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="rollout-view">
    <header class="page-header">
      <h1>灰度版本管理</h1>
      <span v-if="lastSaved" class="saved">上次保存: {{ lastSaved }}</span>
    </header>

    <div class="sliders">
      <div v-for="ver in ['v1', 'v2', 'v3']" :key="ver" class="slider-row">
        <label class="ver-label">{{ ver.toUpperCase() }}</label>
        <input type="range" v-model.number="weights[ver]" min="0" max="100" class="slider" />
        <span class="ver-pct">{{ weights[ver] }}%</span>
      </div>
    </div>

    <div class="preview-bar">
      <div class="bar-seg v1" :style="{ width: weights.v1 + '%' }">
        {{ weights.v1 > 5 ? 'V1 ' + weights.v1 + '%' : '' }}
      </div>
      <div class="bar-seg v2" :style="{ width: weights.v2 + '%' }">
        {{ weights.v2 > 5 ? 'V2 ' + weights.v2 + '%' : '' }}
      </div>
      <div class="bar-seg v3" :style="{ width: weights.v3 + '%' }">
        {{ weights.v3 > 5 ? 'V3 ' + weights.v3 + '%' : '' }}
      </div>
    </div>

    <button class="btn-save" @click="save" :disabled="saving || total === 0">
      {{ saving ? "保存中..." : "保存权重" }}
    </button>

    <section class="audit-section" v-if="auditLog.length > 0">
      <h2>最近变更</h2>
      <div v-for="(entry, i) in auditLog" :key="i" class="audit-entry">
        <span class="audit-time">{{ entry.timestamp }}</span>
        <span class="audit-op">{{ entry.operator }}</span>
        <span class="audit-change">
          v1:{{ (entry.old?.v1 * 100).toFixed(0) }}%→{{ (entry.new?.v1 * 100).toFixed(0) }}%
          v2:{{ (entry.old?.v2 * 100).toFixed(0) }}%→{{ (entry.new?.v2 * 100).toFixed(0) }}%
          v3:{{ (entry.old?.v3 * 100).toFixed(0) }}%→{{ (entry.new?.v3 * 100).toFixed(0) }}%
        </span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.rollout-view { padding: 24px; max-width: 700px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 22px; margin: 0; }
.saved { color: #51cf66; font-size: 13px; }
.sliders { margin-bottom: 20px; }
.slider-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.ver-label { font-weight: 700; min-width: 30px; }
.slider { flex: 1; }
.ver-pct { min-width: 48px; text-align: right; font-weight: 600; }
.preview-bar { display: flex; height: 36px; border-radius: 8px; overflow: hidden; margin-bottom: 16px; }
.bar-seg { display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; font-weight: 600; transition: width 0.3s; min-width: 0; }
.bar-seg.v1 { background: #667eea; }
.bar-seg.v2 { background: #ffa94d; }
.bar-seg.v3 { background: #51cf66; }
.btn-save { width: 100%; padding: 12px; background: #667eea; color: #fff; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
.audit-section { margin-top: 24px; }
.audit-section h2 { font-size: 16px; margin: 0 0 12px; }
.audit-entry { display: flex; gap: 12px; padding: 8px 12px; background: #f8f9fa; border-radius: 6px; margin-bottom: 6px; font-size: 12px; }
.audit-time { color: #888; min-width: 80px; }
.audit-op { font-weight: 600; min-width: 50px; }
.audit-change { color: #555; }
</style>
