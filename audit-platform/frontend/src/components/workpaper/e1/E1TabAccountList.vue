<script setup lang="ts">
/**
 * E1TabAccountList.vue — E1-10 账户核对
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.9
 *
 * - Dynamic rows with 核对结果(一致/不一致)
 * - 不一致 row red highlight + 原因required
 *
 * Requirements: 8.1-8.2
 */
import { inject, toRef, type Ref } from 'vue'
import { useE1AccountList, type AccountListRow } from '../composables/useE1AccountList'
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
  isInconsistent,
  isMissingReason,
  addRow,
  removeRow,
  updateCell,
} = useE1AccountList(options)

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClass({ row }: { row: AccountListRow }): string {
  if (isInconsistent(row)) return 'e1-acct-red-row'
  return ''
}
</script>

<template>
  <div class="e1-tab-account-list">
    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          max-height="550"
          style="width: 100%"
          :row-class-name="getRowClass"
        >
          <el-table-column label="开户银行" width="150">
            <template #default="{ row }">
              <el-input
                :model-value="row.bank"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'bank', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="账号" width="180">
            <template #default="{ row }">
              <el-input
                :model-value="row.accountNo"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'accountNo', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="账户性质" width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.accountType"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'accountType', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="开户日期" width="130">
            <template #default="{ row }">
              <el-date-picker
                :model-value="row.openDate"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'openDate', val || '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="是否征信" width="90" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.inCreditReport"
                :disabled="isReadonly"
                size="small"
                placeholder="-"
                @change="(val: string) => updateCell(row.id, 'inCreditReport', val)"
              >
                <el-option label="Y" value="Y" />
                <el-option label="N" value="N" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="是否审定表" width="100" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.inAdjudication"
                :disabled="isReadonly"
                size="small"
                placeholder="-"
                @change="(val: string) => updateCell(row.id, 'inAdjudication', val)"
              >
                <el-option label="Y" value="Y" />
                <el-option label="N" value="N" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="核对结果" width="110" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.checkResult"
                :disabled="isReadonly"
                size="small"
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'checkResult', val)"
              >
                <el-option label="一致" value="一致" />
                <el-option label="不一致" value="不一致" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="原因" min-width="150">
            <template #default="{ row }">
              <el-input
                :model-value="row.reason"
                :disabled="isReadonly"
                :class="{ 'required-field': isMissingReason(row) }"
                :placeholder="isInconsistent(row) ? '不一致时必填' : ''"
                size="small"
                @change="(val: string) => updateCell(row.id, 'reason', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center" fixed="right">
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
.e1-tab-account-list {
  padding: 12px 0;
}
.add-btn {
  margin-top: 8px;
}
.required-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
:deep(.e1-acct-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-acct-red-row td) {
  color: #f56c6c;
}
</style>
