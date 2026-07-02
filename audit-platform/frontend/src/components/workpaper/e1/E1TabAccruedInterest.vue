<script setup lang="ts">
/**
 * E1TabAccruedInterest.vue — E1-20 应计利息
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.14
 *
 * - Uses useE1InterestCalc with variant='accrued'
 * - Dynamic rows: 开户银行 | 账号 | 用途 | 币种 | 原币金额 | 结息日 | 截止日 |
 *   天数(readonly) | 日利率 | 应计利息原币(readonly) | 汇率 | 应计利息人民币(readonly) | 备注
 * - Total row at bottom
 *
 * Requirements: 10.3-10.4
 */
import { computed, inject, toRef, type Ref } from 'vue'
import {
  useE1InterestCalc,
  type AccruedInterestRow,
} from '../composables/useE1InterestCalc'
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

const options: UseE1BaseOptions & { variant: 'accrued' } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: 'accrued',
}

const {
  rows,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1InterestCalc(options)

// ─── Computed ────────────────────────────────────────────────────────────────

function asAccrued(row: any): AccruedInterestRow { return row }

const totalAccruedRmb = computed(() => {
  return (rows.value as AccruedInterestRow[]).reduce((sum, r) => sum + (r as AccruedInterestRow).accruedRmb, 0)
})
</script>

<template>
  <div class="e1-tab-accrued-interest">
    <el-skeleton :loading="isLoading" :rows="10" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="550" style="width: 100%">
          <el-table-column label="开户银行" width="130">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).bank" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'bank', val)" />
            </template>
          </el-table-column>
          <el-table-column label="账号" width="150">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).accountNo" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'accountNo', val)" />
            </template>
          </el-table-column>
          <el-table-column label="用途" width="100">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).usage" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'usage', val)" />
            </template>
          </el-table-column>
          <el-table-column label="币种" width="80">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).currency" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'currency', val)" />
            </template>
          </el-table-column>
          <el-table-column label="原币金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="asAccrued(row).fcAmount" :disabled="isReadonly"
                :controls="false" size="small"
                @change="(val: number) => updateCell(row.id, 'fcAmount', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="结息日" width="120">
            <template #default="{ row }">
              <el-date-picker :model-value="asAccrued(row).settleDate" :disabled="isReadonly"
                type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'settleDate', val || '')" />
            </template>
          </el-table-column>
          <el-table-column label="截止日" width="120">
            <template #default="{ row }">
              <el-date-picker :model-value="asAccrued(row).cutoffDate" :disabled="isReadonly"
                type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'cutoffDate', val || '')" />
            </template>
          </el-table-column>
          <el-table-column label="天数" width="70" align="center">
            <template #default="{ row }">
              <span class="computed-cell">{{ asAccrued(row).days }}</span>
            </template>
          </el-table-column>
          <el-table-column label="日利率" width="100" align="center">
            <template #default="{ row }">
              <el-input-number :model-value="asAccrued(row).dailyRate" :disabled="isReadonly"
                :controls="false" :precision="8" size="small"
                @change="(val: number) => updateCell(row.id, 'dailyRate', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="应计利息原币" width="130" align="right">
            <template #default="{ row }">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(asAccrued(row).accruedFc) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="汇率" width="90" align="center">
            <template #default="{ row }">
              <el-input-number :model-value="asAccrued(row).fxRate" :disabled="isReadonly"
                :controls="false" :precision="4" size="small"
                @change="(val: number) => updateCell(row.id, 'fxRate', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="应计利息人民币" width="140" align="right">
            <template #default="{ row }">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(asAccrued(row).accruedRmb) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).note" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'note', val)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="footer-row">
          <el-button v-if="!isReadonly" size="small" @click="addRow">+ 添加行</el-button>
          <span class="total-label">应计利息人民币合计：
            <strong class="computed-cell">{{ displayPrefs.fmtAmount(totalAccruedRmb) }}</strong>
          </span>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-accrued-interest {
  padding: 12px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.total-label {
  font-size: 13px;
  color: #303133;
}
</style>
