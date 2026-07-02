<script setup lang="ts">
/**
 * E1TabCashCount.vue — E1-7/8 现金盘点 (variant: rmb/fx)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.7
 *
 * - RMB模式：面值×张数=金额小计 + 汇总卡(实盘/账面/差异/原因)
 * - FX模式：币种+面值+张数+原币+汇率+折算人民币
 * - variant从sheetName检测: E1-7→rmb, E1-8→fx
 *
 * Requirements: 7.1-7.5
 */
import { inject, toRef, computed, type Ref } from 'vue'
import {
  useE1CashCount,
  type CashCountVariant,
  type RmbCountRow,
  type FxCountRow,
} from '../composables/useE1CashCount'
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

const variant = computed<CashCountVariant>(() => {
  const name = props.sheetName || ''
  if (name.includes('E1-8') || name.includes('外币')) return 'fx'
  return 'rmb'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: CashCountVariant } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: variant.value,
}

const {
  rows,
  rmbSummary,
  rmbTotal,
  isLoading,
  hasDiff,
  addRow,
  removeRow,
  updateCell,
  updateSummary,
} = useE1CashCount(options)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function asRmb(row: any): RmbCountRow { return row }
function asFx(row: any): FxCountRow { return row }
</script>

<template>
  <div class="e1-tab-cash-count">
    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- RMB 模式 -->
        <template v-if="variant === 'rmb'">
          <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
            <el-table-column label="面值" width="120" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asRmb(row).denomination"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'denomination', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="张数" width="120" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asRmb(row).quantity"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'quantity', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="金额小计" width="150" align="right">
              <template #default="{ row }">
                <span class="computed-cell">{{ displayPrefs.fmtAmount(asRmb(row).subtotal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="removeRow(row.id)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRow">+ 添加行</el-button>

          <!-- Summary Card -->
          <el-card class="summary-card" shadow="never">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="实盘合计">
                <span class="computed-cell">{{ displayPrefs.fmtAmount(rmbTotal) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="账面余额">
                <el-input-number
                  :model-value="rmbSummary.bookBalance"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateSummary('bookBalance', val ?? 0)"
                />
              </el-descriptions-item>
              <el-descriptions-item label="盘点差异">
                <span :class="['computed-cell', { 'orange-text': hasDiff() }]">
                  {{ displayPrefs.fmtAmount(rmbSummary.countDiff) }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="差异原因">
                <el-input
                  :model-value="rmbSummary.diffReason"
                  :disabled="isReadonly"
                  placeholder="差异≠0时必填"
                  size="small"
                  @change="(val: string) => updateSummary('diffReason', val)"
                />
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </template>

        <!-- FX 模式 -->
        <template v-else>
          <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
            <el-table-column label="币种" width="100">
              <template #default="{ row }">
                <el-input
                  :model-value="asFx(row).currency"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'currency', val)"
                />
              </template>
            </el-table-column>
            <el-table-column label="面值" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).denomination"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'denomination', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="张数" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).quantity"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'quantity', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="原币金额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).fcAmount"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'fcAmount', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="汇率" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).fxRate"
                  :disabled="isReadonly"
                  :controls="false"
                  :precision="4"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'fxRate', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="折算人民币" width="150" align="right">
              <template #default="{ row }">
                <span class="computed-cell">{{ displayPrefs.fmtAmount(asFx(row).rmbAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="removeRow(row.id)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRow">+ 添加行</el-button>
        </template>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-cash-count {
  padding: 12px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.orange-text {
  color: #e6a23c;
  font-weight: 600;
}
.add-btn {
  margin-top: 8px;
}
.summary-card {
  margin-top: 16px;
}
</style>
