<template>
  <div class="diff-reconcile-analysis">
    <h4 class="diff-reconcile-analysis__title">差异原因分析表</h4>
    <p class="diff-reconcile-analysis__desc">
      按差异类型自动聚合笔数和金额。仅"原因说明"和"应对措施"可编辑。
      <el-tooltip content="当上方明细表中修改差异类型后，此表自动重新汇总（实时联动）" placement="top">
        <el-icon style="margin-left:4px;vertical-align:middle;color:#909399;cursor:help"><InfoFilled /></el-icon>
      </el-tooltip>
    </p>

    <el-table :data="analysisGroups" border size="small" show-summary :summary-method="getSummaries" table-layout="auto" class="diff-reconcile-analysis__table">
      <el-table-column label="差异类型" min-width="90">
        <template #default="{ row }">
          <el-tag :type="typeColor(row.diff_type)" size="small">
            {{ typeLabel(row.diff_type) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="笔数" prop="count" min-width="50" align="center" />

      <el-table-column label="差异净额" prop="net_amount" min-width="90" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-reconcile-analysis__negative': row.net_amount < 0 }">
            {{ formatAmount(row.net_amount) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="差异绝对值" prop="abs_amount" min-width="90" align="right">
        <template #default="{ row }">{{ formatAmount(row.abs_amount) }}</template>
      </el-table-column>

      <el-table-column label="占比" prop="percentage" min-width="55" align="center">
        <template #default="{ row }">{{ row.percentage }}%</template>
      </el-table-column>

      <el-table-column label="原因说明" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.note"
            size="small"
            type="textarea"
            :rows="1"
            autosize
            placeholder="填写原因说明"
            @change="(val: string) => $emit('update-note', row.diff_type, val)"
          />
          <span v-else>{{ row.note || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="应对措施" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.action"
            size="small"
            type="textarea"
            :rows="1"
            autosize
            placeholder="填写应对措施"
            @change="(val: string) => $emit('update-action', row.diff_type, val)"
          />
          <span v-else>{{ row.action || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 未分类提示 -->
    <el-alert
      v-if="unclassifiedCount > 0"
      :title="`${unclassifiedCount} 笔差异未分类，请在明细表中选择差异类型`"
      type="warning"
      :closable="false"
      show-icon
      class="diff-reconcile-analysis__warn"
    />
  </div>
</template>

<script setup lang="ts">
import { InfoFilled } from '@element-plus/icons-vue'
import type { DiffAnalysisGroup } from './diffReconcileTypes'

const props = defineProps<{
  analysisGroups: DiffAnalysisGroup[]
  totals: { count: number; net_amount: number; abs_amount: number }
  unclassifiedCount: number
  readonly: boolean
}>()

defineEmits<{
  (e: 'update-note', diffType: string, note: string): void
  (e: 'update-action', diffType: string, action: string): void
}>()

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  columns.forEach((col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (col.property === 'count') { sums[index] = String(props.totals.count); return }
    if (col.property === 'net_amount') { sums[index] = formatAmount(props.totals.net_amount); return }
    if (col.property === 'abs_amount') { sums[index] = formatAmount(props.totals.abs_amount); return }
    if (col.property === 'percentage') { sums[index] = '100%'; return }
    sums[index] = ''
  })
  return sums
}

// ─── 工具函数 ────────────────────────────────────────────────────────────────

const TYPE_MAP: Record<string, { label: string; color: string }> = {
  time: { label: '时间性差异', color: 'info' },
  accounting: { label: '记账差异', color: 'warning' },
  unrecorded: { label: '未达账项', color: 'danger' },
  other: { label: '其他差异', color: '' },
}

function typeLabel(t: string): string { return TYPE_MAP[t]?.label ?? t }
function typeColor(t: string): string { return TYPE_MAP[t]?.color ?? '' }

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.diff-reconcile-analysis__title {
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 4px;
}

.diff-reconcile-analysis__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

/* 表头折行 */
.diff-reconcile-analysis__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 13px;
}

.diff-reconcile-analysis__table :deep(.el-table__body td .cell) {
  font-size: 13px;
}

/* 合计行不折行 */
.diff-reconcile-analysis__table :deep(.el-table__footer td .cell) {
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}

.diff-reconcile-analysis__negative {
  color: var(--el-color-danger);
}

.diff-reconcile-analysis__warn {
  margin-top: 8px;
}
</style>
