<template>
  <div class="g11-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">G11-3 调整分录汇总</h3>
      <div class="head-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-3" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G11-3-adjustment" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="adj.addRow()">+ 新增</el-button>
      </div>
    </div>
    <el-alert v-if="!adj.isBalanced.value" type="error" :closable="false" class="balance-alert">
      借贷不平衡，差额 {{ fmt(adj.balanceDiff.value) }}
    </el-alert>
    <el-alert v-else-if="adj.adjustmentNet.value !== 0" type="info" :closable="false" class="balance-alert">
      已回写 G11-1/G11-2「其他」行调整数 {{ fmt(adj.adjustmentNet.value) }}
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
      <el-table-column label="操作" width="64" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG11Adjustment } from '../../composables/useG11Adjustment'
import { useG11DetailAnalysis } from '../../composables/useG11DetailAnalysis'
import { parseG11AdjStore, patchG11AdjRow } from '../../composables/g11AdjStorage'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useG11DetailAnalysis({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const adj = useG11Adjustment({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  applyAdjustmentToAdjudication: (net) => {
    const store = parseG11AdjStore(props.allResponses.get('G11-adj-rows')?.remark)
    props.debouncedSave('G11-adj-rows', {
      remark: JSON.stringify(patchG11AdjRow(store, 'other', { currentAdjustment: net })),
    })
  },
  applyAdjustmentToDetail: (net) => detail.applyOtherAdjustment(net),
})

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g11-adjustment { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.balance-alert { margin-bottom: 8px; }
</style>
