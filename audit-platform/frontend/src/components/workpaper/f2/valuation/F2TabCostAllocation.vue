<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>生产成本分配</h3><span class="code">F2-44</span></div>
      <div class="stat-row">
        <span class="stat">分配合计 {{ ca.allocGrandTotal.value.toLocaleString() }}</span>
        <el-tag v-if="ca.allocationMismatch.value" type="danger" size="small">分配差异需关注</el-tag>
      </div>
    </header>

    <div class="source-bar">
      <span>来源底稿联动：</span>
      <GtIndexChip value="F2-41" label="F2-41 材料" />
      <GtIndexChip value="F2-42" label="F2-42 人工" />
      <GtIndexChip value="F2-43" label="F2-43 费用" />
      <span class="source-nums">
        材料 {{ ca.sourceTotals.value.material.toLocaleString() }}
        | 人工 {{ ca.sourceTotals.value.labor.toLocaleString() }}
        | 制造费用 {{ ca.sourceTotals.value.overhead.toLocaleString() }}
      </span>
    </div>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="ca.addRow()">+ 新增产品</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-44"
        :disabled="isReadonly"
        ai-section="cost-analysis"
        :existing-content="ca.auditNote.value"
        review-section="F2-44-conclusion"
        @ai-filled="(t: string) => { ca.auditNote.value = t }"
      />
    </div>

    <el-table :data="ca.enrichedRows.value" border size="small" max-height="420">
      <el-table-column label="产品" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.productName" size="small"
            @change="(v: string) => ca.updateRow(row.rowId, { productName: v })" />
          <span v-else>{{ row.productName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="分配基准" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.allocationBase" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { allocationBase: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="基准占比%" width="95" align="right">
        <template #default="{ row }"><span class="formula">{{ row.baseRatio.toFixed(1) }}</span></template>
      </el-table-column>
      <el-table-column label="材料分配" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.materialAlloc" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { materialAlloc: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="人工分配" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.laborAlloc" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { laborAlloc: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="费用分配" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.overheadAlloc" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { overheadAlloc: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="分配合计" width="100" align="right">
        <template #default="{ row }">{{ row.totalAlloc.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="差异" width="90" align="right">
        <template #default="{ row }">
          <span :class="Math.abs(row.variance) > 0.01 ? 'warn-text' : ''">{{ row.variance.toFixed(0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="ca.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="footer">
      <h4>审计说明</h4>
      <el-input v-model="ca.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2CostAllocation } from '../../composables/useF2CostAllocation'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const ca = useF2CostAllocation({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.source-nums { margin-left: auto; font-weight: 500; color: #303133; }
.warn-text { color: #f56c6c; font-weight: 600; }
</style>
