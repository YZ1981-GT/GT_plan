<script setup lang="ts">
/**
 * E1TabCutoffTest.vue — E1-21/22 截止测试 (variant: bank/other)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.15
 *
 * - Uses useE1CutoffTest composable
 * - Props: variant detected from sheetName (E1-21→'bank', E1-22→'other')
 * - el-table: 凭证号 | 日期 | 金额 | 对方账户 | 是否跨期(readonly, computed, red highlight)
 * - Dynamic rows
 *
 * Requirements: 10.4-10.5
 */
import { computed, inject, toRef, type Ref } from 'vue'
import {
  useE1CutoffTest,
  type CutoffVariant,
  type CutoffTestRow,
} from '../composables/useE1CutoffTest'
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
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Variant Detection ───────────────────────────────────────────────────────

const variant = computed<CutoffVariant>(() => {
  const name = props.sheetName || ''
  if (name.includes('E1-22') || name.includes('其他货币资金')) return 'other'
  return 'bank'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: CutoffVariant } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as unknown as Ref<string>,
  variant: variant.value,
}

const {
  rows,
  balanceSheetDate,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CutoffTest(options)

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClass({ row }: { row: CutoffTestRow }): string {
  if (row.isCrossover) return 'e1-cutoff-red-row'
  return ''
}
</script>

<template>
  <div class="e1-tab-cutoff-test">
    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <div class="bs-date-info" v-if="balanceSheetDate">
          <el-tag size="small" type="info">资产负债表日：{{ balanceSheetDate }}</el-tag>
        </div>

        <el-table
          :data="rows"
          border
          stripe
          size="small"
          max-height="500"
          style="width: 100%"
          :row-class-name="getRowClass"
        >
          <el-table-column label="凭证号" width="130">
            <template #default="{ row }">
              <el-input :model-value="row.voucherNo" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'voucherNo', val)" />
            </template>
          </el-table-column>
          <el-table-column label="日期" width="140">
            <template #default="{ row }">
              <el-date-picker :model-value="row.date" :disabled="isReadonly" type="date"
                value-format="YYYY-MM-DD" size="small" style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'date', val || '')" />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.amount" :disabled="isReadonly"
                :controls="false" size="small"
                @change="(val: number) => updateCell(row.id, 'amount', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="对方账户" min-width="150">
            <template #default="{ row }">
              <el-input :model-value="row.counterparty" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'counterparty', val)" />
            </template>
          </el-table-column>
          <el-table-column label="是否跨期" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.isCrossover" type="danger" size="small">跨期</el-tag>
              <span v-else class="computed-cell">否</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRow">+ 添加行</el-button>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-cutoff-test {
  padding: 12px 0;
}
.bs-date-info {
  margin-bottom: 8px;
}
.computed-cell {
  color: #909399;
}
.add-btn {
  margin-top: 8px;
}
:deep(.e1-cutoff-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-cutoff-red-row td) {
  color: #f56c6c;
}
</style>
