<template>
  <div class="h10-adjustment" data-testid="h10-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">H10-3 调整分录汇总</h3>
      <div class="head-actions">
        <H10ImportExportDropdown :wp-id="wpId" sheet="H10-3" @imported="emit('imported')" />
        <GtReviewTrigger section-id="H10-3-adjustment" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="adj.addRow()">+ 新增</el-button>
      </div>
    </div>
    <el-alert v-if="!adj.isBalanced.value" type="error" :closable="false" class="balance-alert">
      借贷不平衡，差额 {{ fmt(adj.balanceDiff.value) }}
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
      <el-table-column label="日期" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { date: v })" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="制单人" width="88">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.preparedBy" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { preparedBy: v })" />
          <span v-else>{{ row.preparedBy }}</span>
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
import { useH10Adjustment } from '../../composables/useH10Adjustment'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import H10ImportExportDropdown from '../H10ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const adj = useH10Adjustment({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h10-adjustment { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.balance-alert { margin-bottom: 8px; }
</style>
