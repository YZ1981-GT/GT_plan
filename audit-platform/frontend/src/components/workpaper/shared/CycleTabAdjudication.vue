<template>
  <div class="cycle-adjudication">
    <h3 class="sheet-title">{{ config.sheetCode }} {{ config.accountLabel }}审定表</h3>
    <el-table :data="rows" border size="small">
      <el-table-column prop="label" label="项目" width="160" fixed />
      <el-table-column label="期初审定" width="110">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.priorAudited"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.rowKey, 'prior-audited', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column :label="debitLabel" width="110">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.periodDebit"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.rowKey, 'debit', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column :label="creditLabel" width="110">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.periodCredit"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.rowKey, 'credit', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="期末未审" width="110">
        <template #default="{ row }">{{ row.closingUnadjusted.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="AJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.closingAje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.rowKey, 'aje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="RJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.closingRje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => updateField(row.rowKey, 'rje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="期末审定" width="110">
        <template #default="{ row }">{{ row.closingAudited.toLocaleString() }}</template>
      </el-table-column>
    </el-table>

    <el-table :data="[totalRow]" border size="small" class="subtotal-table" :show-header="false">
      <el-table-column width="160"><template #default="{ row }"><b>{{ row.label }}</b></template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.priorAudited.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.periodDebit.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.periodCredit.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.closingUnadjusted.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.closingAje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.closingRje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.closingAudited.toLocaleString() }}</template></el-table-column>
    </el-table>

    <div class="tb-diff-row">
      <span>试算平衡表数（{{ config.accountCode }}）：
        <el-input-number v-model="trialBalanceAmount" size="small" :controls="false" :disabled="isReadonly" />
      </span>
      <span :class="{ 'diff-red': trialBalanceDiff !== 0 }">
        差异：{{ trialBalanceDiff.toLocaleString() }}
        <template v-if="trialBalanceDiff === 0"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <div class="audit-notes">
      <h4>审计说明</h4>
      <el-input v-model="auditNote" type="textarea" :rows="2" :disabled="isReadonly" />
      <h4>审计结论</h4>
      <el-input v-model="conclusion" type="textarea" :rows="2" :disabled="isReadonly" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { usePeriodAdjudication } from './usePeriodAdjudication'
import type { CycleAdjudicationConfig } from './cycleAdjudicationConfigs'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  config: CycleAdjudicationConfig
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const configRef = computed(() => props.config)

const {
  rows,
  totalRow,
  trialBalanceAmount,
  trialBalanceDiff,
  auditNote,
  conclusion,
  debitLabel,
  creditLabel,
  updateField,
} = usePeriodAdjudication({
  config: configRef,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.cycle-adjudication { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
.subtotal-table { margin-top: -1px; }
.tb-diff-row { display: flex; gap: 24px; margin: 16px 0; align-items: center; }
.diff-red { color: #f56c6c; font-weight: 600; }
.audit-notes h4 { margin: 12px 0 6px; font-size: 13px; }
</style>
