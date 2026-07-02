<script setup lang="ts">
/**
 * E1TabAnalysis.vue — E1-14 分析表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.11
 *
 * - Uses useE1Analysis composable
 * - Fixed rows: 项目 | 期末金额(from E1-1) | 期初金额 | 变动额 | 变动率 | 变动原因(textarea+AI)
 * - Red highlight when |changeRate|>30%
 * - AI button per row (disabled placeholder)
 *
 * Requirements: 9.1-9.3
 */
import { ref, inject, toRef, type Ref } from 'vue'
import { useE1Analysis, type AnalysisRow } from '../composables/useE1Analysis'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  isLoading,
  isRateExceeding,
  updateCell,
} = useE1Analysis(options)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtRate(rate: number | ''): string {
  if (rate === '' || rate === 0) return '-'
  return (rate * 100).toFixed(2) + '%'
}

function getRowClass({ row }: { row: AnalysisRow }): string {
  if (isRateExceeding(row)) return 'e1-analysis-red-row'
  return ''
}
</script>

<template>
  <div class="e1-tab-analysis">
    <el-skeleton :loading="isLoading" :rows="6" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          :row-class-name="getRowClass"
          style="width: 100%"
        >
          <el-table-column prop="itemName" label="项目" width="150" fixed="left">
            <template #default="{ row }">
              <span class="font-bold">{{ row.itemName }}</span>
            </template>
          </el-table-column>

          <el-table-column label="期末金额" width="150" align="right">
            <template #default="{ row }">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(row.endingAmount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="期初金额" width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openingAmount"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateCell(row.itemKey, 'openingAmount', val ?? 0)"
              />
            </template>
          </el-table-column>

          <el-table-column label="变动额" width="150" align="right">
            <template #default="{ row }">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(row.changeAmount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="变动率" width="100" align="center">
            <template #default="{ row }">
              <span :class="{ 'red-text': isRateExceeding(row) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column label="变动原因" min-width="250">
            <template #default="{ row }">
              <div class="note-cell">
                <el-input
                  type="textarea"
                  :model-value="row.varianceNote"
                  :disabled="isReadonly"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="填写变动原因分析"
                  @change="(val: string) => updateCell(row.itemKey, 'varianceNote', val)"
                />
                <el-button
                  size="small"
                  type="primary"
                  text
                  disabled
                  class="ai-btn"
                  title="AI生成(待接入)"
                >🤖</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-analysis {
  padding: 12px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.red-text {
  color: #f56c6c;
  font-weight: 600;
}
.font-bold {
  font-weight: 700;
}
.note-cell {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.note-cell .el-textarea {
  flex: 1;
}
.ai-btn {
  flex-shrink: 0;
  margin-top: 2px;
}
:deep(.e1-analysis-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-analysis-red-row td) {
  color: #f56c6c;
}
</style>
