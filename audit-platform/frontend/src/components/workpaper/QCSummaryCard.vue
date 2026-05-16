<template>
  <div class="gt-qc-summary-card" v-loading="loading">
    <h3 class="card-title">质量自检概览</h3>
    <div class="metrics-grid" v-if="summary">
      <div class="metric-item" @click="$emit('drill', 'all')">
        <span class="metric-value">{{ summary.total_workpapers }}</span>
        <span class="metric-label">底稿总数</span>
      </div>
      <div class="metric-item success" @click="$emit('drill', 'passed')">
        <span class="metric-value">{{ summary.passed_qc }}</span>
        <span class="metric-label">已通过自检</span>
      </div>
      <div class="metric-item danger" @click="$emit('drill', 'blocking')">
        <span class="metric-value">{{ summary.has_blocking }}</span>
        <span class="metric-label">存在阻断</span>
      </div>
      <div class="metric-item info" @click="$emit('drill', 'not_started')">
        <span class="metric-value">{{ summary.not_started }}</span>
        <span class="metric-label">未编制</span>
      </div>
      <div class="metric-item" :class="passRateClass">
        <span class="metric-value">{{ passRateText }}</span>
        <span class="metric-label">通过率</span>
      </div>
    </div>
    <el-empty v-if="!loading && !summary" description="暂无数据" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getQCSummary, type QCSummary } from '@/services/workpaperApi'

const props = defineProps<{ projectId: string }>()
defineEmits<{ (e: 'drill', filter: string): void }>()

const loading = ref(false)
const summary = ref<QCSummary | null>(null)

const passRateText = computed(() => {
  if (!summary.value) return '-'
  return `${(summary.value.pass_rate * 100).toFixed(0)}%`
})

const passRateClass = computed(() => {
  if (!summary.value) return ''
  return summary.value.pass_rate >= 0.8 ? 'success' : summary.value.pass_rate >= 0.5 ? '' : 'danger'
})

async function fetchSummary() {
  loading.value = true
  try {
    summary.value = await getQCSummary(props.projectId)
  } catch { /* ignore */ }
  finally { loading.value = false }
}

onMounted(fetchSummary)
</script>

<style scoped>
.gt-qc-summary-card {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-4);
}
.card-title { margin: 0 0 12px; color: var(--gt-color-primary); font-size: var(--gt-font-size-md); }
.metrics-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.metric-item {
  flex: 1; min-width: 100px; text-align: center; padding: 12px 8px;
  border-radius: var(--gt-radius-sm); background: var(--gt-color-primary-bg); cursor: pointer;
  transition: box-shadow 0.2s;
}
.metric-item:hover { box-shadow: var(--gt-shadow-md); }
.metric-item.success { background: var(--gt-color-success-light); }
.metric-item.danger { background: var(--gt-bg-danger); }
.metric-item.info { background: var(--gt-color-bg); }
.metric-value { display: block; font-size: 24px /* allow-px: special */; font-weight: 700; color: var(--gt-color-primary); }
.metric-item.success .metric-value { color: var(--gt-color-success); }
.metric-item.danger .metric-value { color: var(--gt-color-coral); }
.metric-item.info .metric-value { color: var(--gt-color-info); }
.metric-label { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px; }
</style>
