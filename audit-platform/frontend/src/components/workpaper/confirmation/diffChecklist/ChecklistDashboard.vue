<template>
  <div class="checklist-dashboard">
    <el-collapse v-model="expanded">
      <el-collapse-item name="dashboard" title="调节进度概览">
        <div class="checklist-dashboard__cards">
          <div class="checklist-dashboard__card">
            <div class="checklist-dashboard__card-value">{{ metrics.total_count }}</div>
            <div class="checklist-dashboard__card-label">总公司数</div>
          </div>
          <div class="checklist-dashboard__card checklist-dashboard__card--success">
            <div class="checklist-dashboard__card-value">{{ metrics.balanced_count }}</div>
            <div class="checklist-dashboard__card-label">已平衡</div>
          </div>
          <div class="checklist-dashboard__card checklist-dashboard__card--warning">
            <div class="checklist-dashboard__card-value">{{ metrics.diff_count }}</div>
            <div class="checklist-dashboard__card-label">有差异</div>
          </div>
          <div
            :class="[
              'checklist-dashboard__card',
              { 'checklist-dashboard__card--danger': metrics.over_materiality_count > 0 },
            ]"
          >
            <div class="checklist-dashboard__card-value">{{ metrics.over_materiality_count }}</div>
            <div class="checklist-dashboard__card-label">超重要性</div>
          </div>
          <div class="checklist-dashboard__card">
            <div class="checklist-dashboard__card-value">{{ metrics.completion_rate }}%</div>
            <div class="checklist-dashboard__card-label">完成率</div>
          </div>
          <div class="checklist-dashboard__card">
            <div class="checklist-dashboard__card-value">{{ formatAmount(metrics.diff_abs_total) }}</div>
            <div class="checklist-dashboard__card-label">差异绝对值合计</div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { DiffChecklistMetrics } from './diffChecklistTypes'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

defineProps<{
  metrics: DiffChecklistMetrics
}>()

const expanded = ref(['dashboard'])
const prefs = useDisplayPrefsStore()

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}
</script>

<style scoped>
.checklist-dashboard {
  margin-bottom: 12px;
}

.checklist-dashboard__cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
}

.checklist-dashboard__card {
  text-align: center;
  padding: 10px 8px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
}

.checklist-dashboard__card--success {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}

.checklist-dashboard__card--warning {
  border-color: var(--el-color-warning-light-5);
  background: var(--el-color-warning-light-9);
}

.checklist-dashboard__card--danger {
  border-color: var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}

.checklist-dashboard__card-value {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.checklist-dashboard__card-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
