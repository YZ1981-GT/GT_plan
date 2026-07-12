<template>
  <div class="g10-adjustment" data-testid="g10-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">G10-3 调整分录汇总</h3>
      <div class="head-actions">
        <G10ImportExportDropdown :wp-id="wpId" sheet="G10-3" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G10-3-adjustment" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="adj.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-alert v-if="!adj.isBalanced.value" type="error" :closable="false" class="balance-alert">
      借贷不平衡，差额 {{ fmt(adj.balanceDiff.value) }}
    </el-alert>
    <el-alert v-else-if="adj.adjustmentNet.value !== 0" type="info" :closable="false" class="balance-alert">
      已回写 G10-1「其他初始金额」行期末调整 {{ fmt(adj.adjustmentNet.value) }}
    </el-alert>

    <el-table :data="adj.rows.value" border size="small" style="font-size:13px" max-height="480">
      <el-table-column label="类型" width="72">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small"
            @change="(v: 'AJE'|'RJE') => adj.updateRow(row.rowId, { entryType: v })">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="108">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { date: v })" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { summary: v })" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { accountName: v })" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => adj.updateRow(row.rowId, { debitAmount: v ?? 0 })" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => adj.updateRow(row.rowId, { creditAmount: v ?? 0 })" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="编制人" width="80">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.preparedBy" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { preparedBy: v })" />
          <span v-else>{{ row.preparedBy }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { remark: v })" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="balance-row">
      借方 {{ fmt(adj.debitTotal.value) }} · 贷方 {{ fmt(adj.creditTotal.value) }}
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>汇总本科目相关的账项调整（AJE）与重分类调整（RJE）；每笔分录借贷必须平衡，合计借方应等于合计贷方。</p>
        <p>调整净额自动回写 G10-1 审定表「其他初始金额」行期末调整列，据以计算审定数（未审 + 账项调整）。</p>
        <p>RJE 仅影响列报重分类不改变损益；AJE 涉及公允价值变动损益的须与 G10-2 明细「计入损益」勾稽。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG10Adjustment } from '../../composables/useG10Adjustment'
import { useG10Adjudication } from '../../composables/useG10Adjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const adjudication = useG10Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const adj = useG10Adjustment({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  applyAdjustmentToAdjudication: (net) => adjudication.applyNetAdjustment(net),
})

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g10-adjustment { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.balance-alert { margin-bottom: 8px; }
.balance-row { margin-top: 8px; padding: 8px; background: #f5f7fa; font-size: 12px; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
</style>
