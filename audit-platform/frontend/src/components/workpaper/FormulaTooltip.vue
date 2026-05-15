<script setup lang="ts">
/**
 * 公式单元格 hover tooltip（来源摘要）
 * 显示公式类型、参数、当前值、数据来源
 */

interface FormulaInfo {
  formula_type: string
  raw_args: string
  value?: number | string | null
  status: 'filled' | 'stale' | 'error' | 'waiting'
  source_ref?: string
  filled_at?: string
  error?: string
}

defineProps<{
  info: FormulaInfo | null
  visible: boolean
  x: number
  y: number
}>()

const sourceLabels: Record<string, string> = {
  trial_balance: '试算平衡表',
  workpaper_ref: '其他底稿',
  ledger: '序时账',
  aux_balance: '辅助余额表',
  prior_year: '上年底稿',
  adjustment: '调整分录',
  disclosure_note: '附注',
}

function getSourceLabel(formulaType: string): string {
  const map: Record<string, string> = {
    TB: '试算平衡表',
    SUM_TB: '试算平衡表',
    WP: '其他底稿',
    LEDGER: '序时账',
    AUX: '辅助余额表',
    PREV: '上年底稿',
    ADJ: '调整分录',
    NOTE: '附注',
  }
  return map[formulaType] || '未知来源'
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible && info"
      class="formula-tooltip"
      :style="{ left: `${x}px`, top: `${y}px` }"
    >
      <div class="tooltip-header">
        <span class="tooltip-type">={{ info.formula_type }}</span>
        <span class="tooltip-source">{{ getSourceLabel(info.formula_type) }}</span>
      </div>
      <div class="tooltip-formula">
        ={{ info.formula_type }}({{ info.raw_args }})
      </div>
      <div v-if="info.value != null" class="tooltip-value">
        当前值: <strong>{{ typeof info.value === 'number' ? info.value.toLocaleString() : info.value }}</strong>
      </div>
      <div v-if="info.source_ref" class="tooltip-ref">
        来源: {{ info.source_ref }}
      </div>
      <div v-if="info.filled_at" class="tooltip-time">
        填充时间: {{ info.filled_at }}
      </div>
      <div v-if="info.error" class="tooltip-error">
        错误: {{ info.error }}
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.formula-tooltip {
  position: fixed;
  z-index: 9999;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 8px 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  max-width: 320px;
  font-size: 12px;
  pointer-events: none;
}

.tooltip-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.tooltip-type {
  font-weight: 600;
  color: var(--el-color-primary);
}

.tooltip-source {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  padding: 1px 6px;
  border-radius: 3px;
}

.tooltip-formula {
  font-family: 'Consolas', monospace;
  color: var(--el-text-color-regular);
  margin-bottom: 4px;
  word-break: break-all;
}

.tooltip-value {
  color: var(--el-text-color-primary);
}

.tooltip-value strong {
  color: var(--el-color-success);
  font-family: 'Arial Narrow', sans-serif;
  font-variant-numeric: tabular-nums;
}

.tooltip-ref {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  margin-top: 2px;
}

.tooltip-time {
  color: var(--el-text-color-placeholder);
  font-size: 11px;
}

.tooltip-error {
  color: var(--el-color-danger);
  font-size: 11px;
  margin-top: 2px;
}
</style>
