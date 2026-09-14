<!-- K1 附注披露 — 溯源面板 -->
<template>
  <el-card shadow="never" class="trace-panel" data-testid="k1-disclosure-trace">
    <template #header>
      <div class="trace-head">
        <span class="trace-title">附注溯源面板</span>
        <el-tag v-if="openCount" size="small" type="warning">{{ openCount }} 项待核对</el-tag>
        <el-tag v-else size="small" type="success">勾稽正常</el-tag>
      </div>
    </template>
    <el-table :data="rows" border size="small" class="trace-table">
      <el-table-column prop="title" label="附注区块" min-width="120" />
      <el-table-column prop="noteTarget" label="附注章节" min-width="160" show-overflow-tooltip />
      <el-table-column prop="source" label="源底稿" min-width="180" show-overflow-tooltip />
      <el-table-column label="K1-1 审定" min-width="130" align="right">
        <template #default="{ row }">
          <span class="amt">{{ row.adjudicationValue != null ? fmt(row.adjudicationValue) : '—' }}</span>
          <div class="sub-label">{{ row.adjudicationLabel }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="88" align="center">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="detail" label="说明" min-width="160" show-overflow-tooltip />
      <el-table-column label="跳转" width="120" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="emit('navigate-sheet', row.sourceSheet)">
            源底稿
          </el-button>
          <el-button size="small" type="primary" link @click="emit('navigate-sheet', '审定表K1-1')">
            K1-1
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import type { K1DisclosureTraceRow, K1TraceStatus } from '../../composables/k1DisclosureTrace'

defineProps<{
  rows: K1DisclosureTraceRow[]
  openCount: number
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

function fmt(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusType(s: K1TraceStatus): 'success' | 'warning' | 'info' {
  if (s === 'ok') return 'success'
  if (s === 'warn') return 'warning'
  return 'info'
}

function statusLabel(s: K1TraceStatus): string {
  if (s === 'ok') return '一致'
  if (s === 'warn') return '差异'
  return '待填'
}
</script>

<style scoped>
.trace-panel { margin-bottom: 12px; }
.trace-panel :deep(.el-card__header) { padding: 8px 14px; }
.trace-panel :deep(.el-card__body) { padding: 10px 14px; }
.trace-head { display: flex; align-items: center; gap: 8px; }
.trace-title { font-weight: 600; }
.trace-table { font-size: var(--wp-font-size, 13px); }
.amt { font-variant-numeric: tabular-nums; }
.sub-label { font-size: 11px; color: var(--el-text-color-secondary); }
</style>
