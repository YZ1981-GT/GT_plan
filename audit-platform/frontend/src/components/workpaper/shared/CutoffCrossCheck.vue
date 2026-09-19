<template>
  <el-card v-if="summary.items.length > 0 || summary.mismatchCount > 0" shadow="never" class="cross-check-card">
    <template #header><span>{{ title }}</span></template>
    <div class="cross-stats">
      <span>凭证匹配 {{ summary.matchedCount }} 对</span>
      <span class="stat-ok">结论一致 {{ summary.consistentCount }}</span>
      <span v-if="summary.mismatchCount" class="stat-warn">结论不一致 {{ summary.mismatchCount }}</span>
      <span v-if="summary.forwardOnlyCount" class="stat-muted">仅 {{ forwardLabel }} {{ summary.forwardOnlyCount }}</span>
      <span v-if="summary.backwardOnlyCount" class="stat-muted">仅 {{ backwardLabel }} {{ summary.backwardOnlyCount }}</span>
    </div>
    <el-table v-if="highlightItems.length > 0" :data="highlightItems" border size="small" max-height="200" class="cross-table">
      <el-table-column prop="voucherNo" label="凭证号" min-width="100" />
      <el-table-column prop="forwardConclusion" :label="`${forwardLabel}结论`" width="100" />
      <el-table-column prop="backwardConclusion" :label="`${backwardLabel}结论`" width="100" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <p v-else class="cross-ok">已匹配凭证结论一致，可与对向底稿交叉评价。</p>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CutoffCrossCheckSummary } from '../composables/cutoffCrossCheck'

const props = defineProps<{
  title: string
  forwardLabel: string
  backwardLabel: string
  summary: CutoffCrossCheckSummary
}>()

const highlightItems = computed(() =>
  props.summary.items.filter((i) => i.status !== 'consistent').slice(0, 20),
)

function statusTag(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'consistent') return 'success'
  if (status === 'mismatch') return 'danger'
  return 'warning'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    consistent: '一致',
    mismatch: '不一致',
    'forward-only': '仅账→单',
    'backward-only': '仅单→账',
  }
  return map[status] ?? status
}
</script>

<style scoped>
.cross-check-card { margin-bottom: 14px; }
.cross-check-card :deep(.el-card__header) { padding: 10px 16px; background: #f0fdf4; font-weight: 600; }
.cross-stats { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 10px; font-size: 12px; color: #374151; }
.stat-ok { color: #059669; font-weight: 600; }
.stat-warn { color: #dc2626; font-weight: 600; }
.stat-muted { color: #6b7280; }
.cross-ok { margin: 0; font-size: 12px; color: #059669; }
.cross-table { font-size: 12px; }
</style>
