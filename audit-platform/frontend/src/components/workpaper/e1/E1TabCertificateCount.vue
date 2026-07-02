<script setup lang="ts">
/**
 * E1TabCertificateCount.vue — E1-9 存单盘点
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.8
 *
 * - Uses useE1CashCount composable with variant='cert'
 * - Dynamic rows: 存单编号 | 开户银行 | 存单类型 | 存入日 | 到期日 | 金额 | 利率 | 盘点结果
 *
 * Requirements: 7.3
 */
import { inject, toRef, type Ref } from 'vue'
import { useE1CashCount, type CertCountRow } from '../composables/useE1CashCount'
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

const options: UseE1BaseOptions & { variant: 'cert' } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: 'cert',
}

const {
  rows,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CashCount(options)

function asCert(row: any): CertCountRow { return row }
</script>

<template>
  <div class="e1-tab-certificate-count">
    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
          <el-table-column label="存单编号" width="130">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).certNo"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'certNo', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="开户银行" width="140">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).bank"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'bank', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="存单类型" width="110">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).certType"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'certType', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="存入日" width="130">
            <template #default="{ row }">
              <el-date-picker
                :model-value="asCert(row).depositDate"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'depositDate', val || '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="到期日" width="130">
            <template #default="{ row }">
              <el-date-picker
                :model-value="asCert(row).maturityDate"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'maturityDate', val || '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="asCert(row).amount"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateCell(row.id, 'amount', val ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="利率(%)" width="100" align="center">
            <template #default="{ row }">
              <el-input-number
                :model-value="asCert(row).interestRate"
                :disabled="isReadonly"
                :controls="false"
                :precision="4"
                size="small"
                @change="(val: number) => updateCell(row.id, 'interestRate', val ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="盘点结果" width="110" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="asCert(row).result"
                :disabled="isReadonly"
                size="small"
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'result', val)"
              >
                <el-option label="已见" value="已见" />
                <el-option label="未见" value="未见" />
              </el-select>
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
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-certificate-count {
  padding: 12px 0;
}
.add-btn {
  margin-top: 8px;
}
</style>
