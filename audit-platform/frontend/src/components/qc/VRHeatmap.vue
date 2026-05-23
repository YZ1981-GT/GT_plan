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
  </div>
</template>

<script setup lang="ts">
interface HeatmapRow {
  cycle: string
  blocking: number
  warning: number
  info: number
}

defineProps<{
  matrix: HeatmapRow[]
  total: { blocking: number; warning: number; info: number } | null
  loading?: boolean
}>()

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

.sev-blocking { color: #c62828; }
.sev-warning { color: #e65100; }
.sev-info { color: #616161; }
</style>
