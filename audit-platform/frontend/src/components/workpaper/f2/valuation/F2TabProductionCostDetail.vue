<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>生产成本明细表</h3><span class="code">F2-41</span></div>
      <div class="stat-row">
        <span class="stat">期末合计 {{ pc.totals.value.totalClosing.toLocaleString() }}</span>
        <span class="stat sub">材料 {{ pc.totals.value.dmClosing.toLocaleString() }}</span>
        <span class="stat sub">人工 {{ pc.totals.value.dlClosing.toLocaleString() }}</span>
        <span class="stat sub">费用 {{ pc.totals.value.ohClosing.toLocaleString() }}</span>
      </div>
    </header>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="pc.addRow()">+ 新增产品</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-41"
        :disabled="isReadonly"
        ai-section="cost-analysis"
        :existing-content="pc.auditNote.value"
        ai-title="AI 生成 · 生产成本分析结论"
        review-section="F2-41-conclusion"
        @ai-filled="(t: string) => { pc.auditNote.value = t }"
      />
      <el-segmented v-model="pc.activeSegment.value" :options="segments" size="small" />
    </div>

    <el-table :data="pc.enrichedRows.value" border size="small" max-height="460">
      <el-table-column label="产品" width="130" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.productName" size="small"
            @change="(v: string) => pc.updateRow(row.rowId, { productName: v })" />
          <span v-else>{{ row.productName }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="`${segLabel}-期初`" width="95">
        <template #default="{ row }">
          <el-input-number :model-value="row[segKeys.opening]" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => pc.updateRow(row.rowId, { [segKeys.opening]: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column :label="`${segLabel}-投入`" width="95">
        <template #default="{ row }">
          <el-input-number :model-value="row[segKeys.input]" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => pc.updateRow(row.rowId, { [segKeys.input]: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column :label="`${segLabel}-转出`" width="95">
        <template #default="{ row }">
          <el-input-number :model-value="row[segKeys.transfer]" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => pc.updateRow(row.rowId, { [segKeys.transfer]: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column :label="`${segLabel}-期末`" width="100" align="right">
        <template #default="{ row }">
          <span class="formula">{{ row[segKeys.closing].toLocaleString() }}</span>
        </template>
      </el-table-column>
      <el-table-column label="三费合计-期末" width="115" align="right">
        <template #default="{ row }"><span class="formula">{{ row.totalClosing.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="pc.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="footer">
      <h4>审计说明</h4>
      <el-input v-model="pc.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useF2ProductionCostDetail, type ProductionSegment } from '../../composables/useF2ProductionCostDetail'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const pc = useF2ProductionCostDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const segments = [
  { label: '直接材料', value: 'material' },
  { label: '直接人工', value: 'labor' },
  { label: '制造费用', value: 'overhead' },
]

const segMap: Record<ProductionSegment, { label: string; opening: string; input: string; transfer: string; closing: string }> = {
  material: { label: '材料', opening: 'dmOpening', input: 'dmInput', transfer: 'dmTransfer', closing: 'dmClosing' },
  labor: { label: '人工', opening: 'dlOpening', input: 'dlInput', transfer: 'dlTransfer', closing: 'dlClosing' },
  overhead: { label: '费用', opening: 'ohOpening', input: 'ohInput', transfer: 'ohTransfer', closing: 'ohClosing' },
}

const segKeys = computed(() => segMap[pc.activeSegment.value])
const segLabel = computed(() => segKeys.value.label)
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
