<template>
  <div class="h10-check" data-testid="h10-check">
    <div class="section-head">
      <h3 class="sheet-title">H10-4 资产处置检查表</h3>
      <div class="head-actions">
        <GtVoucherSamplingEngine :project-id="projectId" :account-codes="['6115']" dialog-mode />
        <GtReviewTrigger section-id="H10-4-check" />
      </div>
    </div>
    <el-alert v-if="check.nonCompliantSummary.value" type="warning" :closable="false" class="summary-alert">
      {{ check.nonCompliantSummary.value }}
    </el-alert>
    <el-table :data="check.rows.value" border size="small" style="font-size:13px" max-height="560">
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed />
      <el-table-column label="资产名称" min-width="120" fixed>
        <template #default="{ row }">
          <span>{{ row.assetName || `行${row.seq}` }}</span>
        </template>
      </el-table-column>
      <el-table-column v-for="col in checkColumns" :key="col.field" :label="col.label" width="96" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row[col.field]" size="small"
            @change="(v: string) => check.updateRow(row.id, { [col.field]: v })">
            <el-option v-for="o in check.complianceOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-tag v-else size="small" :type="tagType(row[col.field])">{{ labelOf(row[col.field]) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="合规" width="72" align="center" fixed="right">
        <template #default="{ row }">
          <el-tag :type="check.rowIsCompliant(row) ? 'success' : 'danger'" size="small">
            {{ check.rowIsCompliant(row) ? '合规' : '不合规' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="凭证索引" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherRef" size="small"
            @update:model-value="(v: string) => check.updateRow(row.id, { voucherRef: v })" />
          <GtIndexChip v-else-if="row.voucherRef" :value="row.voucherRef" />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
            @update:model-value="(v: string) => check.updateRow(row.id, { remark: v })" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="compliance-bar">合规率 {{ (check.complianceRate.value * 100).toFixed(0) }}%</div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useH10Check, type H10CheckRow } from '../../composables/useH10Check'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const check = useH10Check({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const checkColumns: Array<{ field: keyof H10CheckRow; label: string }> = [
  { field: 'approvalProcess', label: '审批程序' },
  { field: 'appraisalBasis', label: '评估依据' },
  { field: 'pricingReasonableness', label: '定价合理' },
  { field: 'taxTreatment', label: '税务处理' },
  { field: 'accountingTiming', label: '会计时点' },
  { field: 'revenueRecognition', label: '收入确认' },
  { field: 'expenseAllocation', label: '费用分摊' },
  { field: 'relatedParty', label: '关联方' },
  { field: 'auditConclusion', label: '审计结论' },
]

function labelOf(v: string) {
  return check.complianceOptions.find((o) => o.value === v)?.label ?? (v || '-')
}

function tagType(v: string) {
  if (v === 'compliant') return 'success'
  if (v === 'non_compliant') return 'danger'
  return 'info'
}
</script>

<style scoped>
.h10-check { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; }
.summary-alert { margin-bottom: 8px; }
.compliance-bar { margin-top: 8px; font-size: 12px; color: #606266; }
</style>
