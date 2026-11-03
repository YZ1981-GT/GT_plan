<template>
  <div class="gt-vr-heatmap" v-loading="!!loading">
    <div class="gt-heatmap-header">
      <h3>风险热力图</h3>
      <el-button size="small" @click="$emit('refresh')">刷新</el-button>
    </div>

    <!-- 11×3 矩阵 -->
    <div class="gt-heatmap-grid">
      <!-- 列标题 -->
      <div class="gt-heatmap-cell gt-heatmap-corner"></div>
      <div class="gt-heatmap-cell gt-heatmap-col-header sev-blocking">阻断</div>
      <div class="gt-heatmap-cell gt-heatmap-col-header sev-warning">警告</div>
      <div class="gt-heatmap-cell gt-heatmap-col-header sev-info">提示</div>

      <!-- 数据行 -->
      <template v-for="row in matrix" :key="row.cycle">
        <div class="gt-heatmap-cell gt-heatmap-row-header">{{ row.cycle }}</div>
        <div
          class="gt-heatmap-cell gt-heatmap-data"
          :style="{ background: colorScale('blocking', row.blocking) }"
          @click="$emit('cell-click', { cycle: row.cycle, severity: 'blocking' })"
        >
          {{ row.blocking || '' }}
        </div>
        <div
          class="gt-heatmap-cell gt-heatmap-data"
          :style="{ background: colorScale('warning', row.warning) }"
          @click="$emit('cell-click', { cycle: row.cycle, severity: 'warning' })"
        >
          {{ row.warning || '' }}
        </div>
        <div
          class="gt-heatmap-cell gt-heatmap-data"
          :style="{ background: colorScale('info', row.info) }"
          @click="$emit('cell-click', { cycle: row.cycle, severity: 'info' })"
        >
          {{ row.info || '' }}
        </div>
      </template>
    </div>

    <!-- 汇总 -->
    <div class="gt-heatmap-total" v-if="total">
      合计：<span class="sev-blocking">{{ total.blocking }} 阻断</span> /
      <span class="sev-warning">{{ total.warning }} 警告</span> /
      <span class="sev-info">{{ total.info }} 提示</span>
    </div>
    <!-- 格子只数「失败」；未执行 / 检查异常 / 不适用另计条数（需求 16.5，后端每行带 status_counts） -->
    <div class="gt-heatmap-status-total" v-if="otherStateTotals.length">
      另有：<span v-for="s in otherStateTotals" :key="s.status" class="gt-heatmap-status-count">
        {{ s.label }} {{ s.count }} 项
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { checkStatusLabel, type GateCheckStatus } from '@/utils/consistencyCheckStatus'

interface HeatmapRow {
  cycle: string
  blocking: number
  warning: number
  info: number
  /** 本循环检查项的五态计数（passed / failed / not_executed / not_applicable / error） */
  status_counts?: Record<string, number>
}

const props = defineProps<{
  matrix: HeatmapRow[]
  total: { blocking: number; warning: number; info: number } | null
  loading?: boolean
}>()

const OTHER_STATES: GateCheckStatus[] = ['not_executed', 'error', 'not_applicable']

/** 各循环「失败」以外三种非通过状态的合计，只列有的 */
const otherStateTotals = computed(() =>
  OTHER_STATES
    .map(status => ({
      status,
      label: checkStatusLabel({ status }),
      count: props.matrix.reduce((n, row) => n + (row.status_counts?.[status] ?? 0), 0),
    }))
    .filter(s => s.count > 0),
)

defineEmits<{
  'cell-click': [payload: { cycle: string; severity: string }]
  refresh: []
}>()

/** 颜色映射：数量 → 背景色深浅 */
function colorScale(severity: string, count: number): string {
  if (count === 0) return '#fff'
  const scales: Record<string, string[]> = {
    blocking: ['#ffcdd2', '#ef5350', '#c62828'],
    warning: ['#fff3e0', '#ff9800', '#e65100'],
    info: ['#f5f5f5', '#bdbdbd', '#616161'],
  }
  const s = scales[severity] || scales.info
  if (count <= 2) return s[0]
  if (count <= 5) return s[1]
  return s[2]
}
</script>

<style scoped>
.gt-vr-heatmap { padding: 16px; }

.gt-heatmap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.gt-heatmap-header h3 { margin: 0; font-size: 15px; }

.gt-heatmap-grid {
  display: grid;
  grid-template-columns: 40px repeat(3, 1fr);
  gap: 2px;
}

.gt-heatmap-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  font-size: 13px;
  border-radius: 3px;
  min-height: 32px;
}

.gt-heatmap-corner { background: transparent; }
.gt-heatmap-col-header { font-weight: 600; font-size: 12px; }
.gt-heatmap-row-header { font-weight: 600; color: #4b2d77; }

.gt-heatmap-data {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  font-weight: 600;
}
.gt-heatmap-data:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.gt-heatmap-total {
  margin-top: 12px;
  font-size: 13px;
  color: #666;
}

.gt-heatmap-status-total {
  margin-top: 4px;
  font-size: 13px;
  color: #666;
}
.gt-heatmap-status-count + .gt-heatmap-status-count { margin-left: 12px; }

.sev-blocking { color: #c62828; }
.sev-warning { color: #e65100; }
.sev-info { color: #616161; }
</style>
