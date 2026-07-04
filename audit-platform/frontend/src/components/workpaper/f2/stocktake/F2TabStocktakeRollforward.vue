<template>
  <div class="f2-st-26">
    <h3 class="title">盘点倒轧表 F2-26</h3>
    <F2StocktakeSheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F2-26" />
    <F2StocktakeSectionForm
      sheet-code="F2-26"
      fields-key="F2-26-fields"
      note-key="F2-26-narrative-note"
      :field-defs="F2_26_NARRATIVE_FIELDS"
      :wp-id="wpId"
      :project-id="projectId"
      :all-responses="allResponses"
      :is-readonly="isReadonly"
      :show-audit-note="false"
      :show-attachments="false"
      compact
    />
    <div class="table-block">
      <div class="toolbar-row">
        <F2SheetToolbar
          v-if="wpId"
          :wp-id="wpId"
          :project-id="projectId"
          api-prefix="f2-st"
          sheet="F2-26"
          :disabled="isReadonly"
          :show-import-export="true"
          ai-section="stocktake-rollforward"
          :existing-content="sheet.auditNote.value"
          :related-context="{ varianceRows: varianceCount }"
          ai-title="AI 生成 · 倒轧结论"
          review-section="F2-26-conclusion"
          @ai-filled="(t: string) => { sheet.auditNote.value = t }"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">+ 新增明细行</el-button>
        <span class="hint">倒轧明细表（公式：理论结存 = 盘点日 + 入库 − 出库）</span>
      </div>
      <el-table :data="enriched" border size="small" max-height="420"
        :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''">
        <el-table-column label="品名" min-width="110">
          <template #default="{ row }">
            <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { itemName: v })" />
          </template>
        </el-table-column>
        <el-table-column label="盘点日数量" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.countDayQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { countDayQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="入库" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.inboundQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { inboundQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="出库" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.outboundQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { outboundQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="理论结存" width="95" align="right">
          <template #default="{ row }">{{ row.theoreticalQty.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="账面结存" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { bookQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="差异" width="80" align="right">
          <template #default="{ row }">{{ row.variance.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { remark: v })" />
          </template>
        </el-table-column>
        <el-table-column width="50">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" link type="danger" size="small" @click="sheet.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="wpId && !isReadonly" label="OCR" width="50" align="center">
          <template #default="{ row }">
            <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
              :disabled="ocrLoadingId === row.id"
              @change="(f: any) => onOcr(row.id, f?.raw)">
              <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
            </el-upload>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <h4>倒轧结论</h4>
    <el-input v-model="sheet.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, type Ref } from 'vue'
import { useF2StocktakeRows } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeOcr } from '../../composables/useF2StocktakeOcr'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import { F2_26_NARRATIVE_FIELDS, type StocktakeRollforwardRow } from './f2StocktakeConfigs'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sheet = useF2StocktakeRows<StocktakeRollforwardRow>({
  rowsKey: 'F2-26-rows',
  noteKey: 'F2-26-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow: () => ({
    id: `st-${Date.now()}`, itemName: '', countDayQty: 0, inboundQty: 0, outboundQty: 0, theoreticalQty: 0, bookQty: 0, remark: '',
  }),
})

const enriched = computed(() => sheet.rows.value.map((r) => {
  const theoreticalQty = r.countDayQty + r.inboundQty - r.outboundQty
  const variance = r.bookQty - theoreticalQty
  return { ...r, theoreticalQty, variance, hasVariance: Math.abs(variance) > 0.001 }
}))

const varianceCount = computed(() => enriched.value.filter((r) => r.hasVariance).length)

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2StocktakeOcr(wpIdRef)

function onOcr(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge('F2-26', rowId, file, (id, patch) => sheet.updateRow(id, patch))
}
</script>

<style scoped>
.f2-st-26 { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.table-block { margin-top: 8px; border-top: 1px solid #ebeef5; padding-top: 12px; }
.toolbar-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.hint { font-size: 12px; color: #909399; }
:deep(.warn-row) { background: #fef0f0; }
h4 { margin: 12px 0 6px; }
</style>
