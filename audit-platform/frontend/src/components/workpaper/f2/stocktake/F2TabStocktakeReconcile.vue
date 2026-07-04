<template>
  <div class="f2-st-24">
    <h3 class="title">账面余额与仓储台账核对 F2-24</h3>
    <F2StocktakeSheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F2-24" />
    <F2StocktakeSectionForm
      sheet-code="F2-24"
      fields-key="F2-24-fields"
      note-key="F2-24-narrative-note"
      :field-defs="F2_24_NARRATIVE_FIELDS"
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
          sheet="F2-24"
          :disabled="isReadonly"
          :show-import-export="true"
          ai-section="stocktake-reconcile"
          :existing-content="sheet.auditNote.value"
          :related-context="{ varianceRows: varianceCount }"
          ai-title="AI 生成 · 账面核对结论"
          review-section="F2-24-conclusion"
          @ai-filled="(t: string) => { sheet.auditNote.value = t }"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">+ 新增明细行</el-button>
        <span class="hint">明细核对表（品名级差异）</span>
      </div>
      <el-table :data="enriched" border size="small" max-height="420"
        :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''">
        <el-table-column label="品名" min-width="110">
          <template #default="{ row }">
            <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { itemName: v })" />
          </template>
        </el-table-column>
        <el-table-column label="规格" width="90">
          <template #default="{ row }">
            <el-input :model-value="row.spec" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { spec: v })" />
          </template>
        </el-table-column>
        <el-table-column label="账面数量" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { bookQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="账面金额" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookAmount" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { bookAmount: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="ERP数量" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.erpQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { erpQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="ERP金额" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.erpAmount" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { erpAmount: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="数量差异" width="90" align="right">
          <template #default="{ row }">{{ row.qtyDiff.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="金额差异" width="100" align="right">
          <template #default="{ row }">{{ row.amtDiff.toLocaleString() }}</template>
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
    <h4>核对结论</h4>
    <el-input v-model="sheet.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, type Ref } from 'vue'
import { useF2StocktakeRows } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeOcr } from '../../composables/useF2StocktakeOcr'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import { F2_24_NARRATIVE_FIELDS, type StocktakeReconcileRow } from './f2StocktakeConfigs'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sheet = useF2StocktakeRows<StocktakeReconcileRow>({
  rowsKey: 'F2-24-rows',
  noteKey: 'F2-24-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow: () => ({
    id: `st-${Date.now()}`, itemName: '', spec: '', bookQty: 0, bookAmount: 0, erpQty: 0, erpAmount: 0, remark: '',
  }),
})

const enriched = computed(() => sheet.rows.value.map((r) => {
  const qtyDiff = r.bookQty - r.erpQty
  const amtDiff = r.bookAmount - r.erpAmount
  return { ...r, qtyDiff, amtDiff, hasVariance: Math.abs(qtyDiff) > 0.001 || Math.abs(amtDiff) > 0.01 }
}))

const varianceCount = computed(() => enriched.value.filter((r) => r.hasVariance).length)

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2StocktakeOcr(wpIdRef)

function onOcr(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge('F2-24', rowId, file, (id, patch) => sheet.updateRow(id, patch))
}
</script>

<style scoped>
.f2-st-24 { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.table-block { margin-top: 8px; border-top: 1px solid #ebeef5; padding-top: 12px; }
.toolbar-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.hint { font-size: 12px; color: #909399; }
:deep(.warn-row) { background: #fef0f0; }
h4 { margin: 12px 0 6px; }
</style>
