<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>制造费用明细表</h3><span class="code">F2-43</span></div>
      <div class="stat-row">
        <span class="stat sub">预算 {{ oh.totals.value.budget.toLocaleString() }}</span>
        <span class="stat sub">实际 {{ oh.totals.value.actual.toLocaleString() }}</span>
        <span class="stat">分配 {{ oh.totals.value.allocated.toLocaleString() }}</span>
        <el-tag v-if="oh.mismatchCount.value" type="danger" size="small">{{ oh.mismatchCount.value }} 行分配不符</el-tag>
      </div>
    </header>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="oh.addRow()">+ 新增费用项</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-43"
        :disabled="isReadonly"
        ai-section="cost-analysis"
        :existing-content="oh.auditNote.value"
        review-section="F2-43-conclusion"
        @ai-filled="(t: string) => { oh.auditNote.value = t }"
      />
    </div>

    <el-table
      :data="oh.enrichedRows.value" border size="small" max-height="460"
      :row-class-name="({ row }) => row.allocMismatch ? 'error-row' : ''"
    >
      <el-table-column label="费用项目" width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.costItem" size="small"
            @change="(v: string) => oh.updateRow(row.rowId, { costItem: v })" />
          <span v-else>{{ row.costItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预算" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.budgetAmt" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => oh.updateRow(row.rowId, { budgetAmt: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="实际" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.actualAmt" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => oh.updateRow(row.rowId, { actualAmt: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="分配额" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.allocatedAmt" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => oh.updateRow(row.rowId, { allocatedAmt: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="85" align="right">
        <template #default="{ row }">
          <span v-if="row.varianceRate !== '' && row.varianceRate !== 'N/A'" class="formula">
            {{ (Number(row.varianceRate) * 100).toFixed(1) }}%
          </span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="oh.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="footer">
      <h4>审计说明</h4>
      <el-input v-model="oh.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2OverheadDetail } from '../../composables/useF2OverheadDetail'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const oh = useF2OverheadDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
