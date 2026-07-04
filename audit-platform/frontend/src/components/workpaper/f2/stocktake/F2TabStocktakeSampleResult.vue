<template>
  <div class="f2-st-25">
    <h3 class="title">抽盘结果汇总 F2-25</h3>
    <F2StocktakeSheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F2-25" />
    <F2StocktakeSectionForm
      sheet-code="F2-25"
      fields-key="F2-25-fields"
      note-key="F2-25-narrative-note"
      :field-defs="F2_25_NARRATIVE_FIELDS"
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
          sheet="F2-25"
          :disabled="isReadonly"
          :show-import-export="true"
          ai-section="stocktake-sample"
          :existing-content="sheet.auditNote.value"
          :related-context="{ varianceRows: varianceCount }"
          ai-title="AI 生成 · 抽盘汇总结论"
          review-section="F2-25-conclusion"
          @ai-filled="(t: string) => { sheet.auditNote.value = t }"
        />
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || diffLoading"
          :loading="diffLoading"
          @click="runDiffAi"
        >
          LLM 差异分析
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">+ 新增明细行</el-button>
        <span class="hint">抽盘明细表（底稿 F-汇总表，保留表格）</span>
      </div>
      <el-table :data="enriched" border size="small" max-height="420"
        :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''">
        <el-table-column label="品名" min-width="100">
          <template #default="{ row }">
            <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { itemName: v })" />
          </template>
        </el-table-column>
        <el-table-column label="规格" width="80">
          <template #default="{ row }">
            <el-input :model-value="row.spec" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { spec: v })" />
          </template>
        </el-table-column>
        <el-table-column label="单位" width="70">
          <template #default="{ row }">
            <el-input :model-value="row.unit" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { unit: v })" />
          </template>
        </el-table-column>
        <el-table-column label="账面数量" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { bookQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="抽盘数量" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.sampleQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { sampleQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="差异数量" width="90" align="right">
          <template #default="{ row }">{{ row.varianceQty.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="100">
          <template #default="{ row }">
            <el-input :model-value="row.varianceReason" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => sheet.updateRow(row.id, { varianceReason: v })" />
          </template>
        </el-table-column>
        <el-table-column label="备注" width="90">
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
    <h4>汇总结论</h4>
    <el-input v-model="sheet.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF2StocktakeRows } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeOcr } from '../../composables/useF2StocktakeOcr'
import { useF2StocktakeAiGenerate } from '../../composables/useF2StocktakeAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import { F2_25_NARRATIVE_FIELDS, type StocktakeSampleRow } from './f2StocktakeConfigs'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sheet = useF2StocktakeRows<StocktakeSampleRow>({
  rowsKey: 'F2-25-rows',
  noteKey: 'F2-25-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow: () => ({
    id: `st-${Date.now()}`, itemName: '', spec: '', unit: '', bookQty: 0, sampleQty: 0, varianceReason: '', remark: '',
  }),
})

const enriched = computed(() => sheet.rows.value.map((r) => {
  const varianceQty = r.sampleQty - r.bookQty
  return { ...r, varianceQty, hasVariance: Math.abs(varianceQty) > 0.001 }
}))

const varianceCount = computed(() => enriched.value.filter((r) => r.hasVariance).length)

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const projectIdRef = toRef(() => props.projectId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2StocktakeOcr(wpIdRef)
const { diffLoading, generateDiffSummary } = useF2StocktakeAiGenerate({ wpId: wpIdRef, projectId: projectIdRef })

function onOcr(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge('F2-25', rowId, file, (id, patch) => sheet.updateRow(id, patch))
}

async function runDiffAi() {
  const differences = enriched.value
    .filter((r) => r.hasVariance)
    .map((r) => ({
      itemName: r.itemName,
      bookQty: r.bookQty,
      actualQty: r.sampleQty,
      reason: r.varianceReason,
    }))
  const result = await generateDiffSummary(differences, sheet.auditNote.value)
  if (result) {
    sheet.auditNote.value = result.summary
    if (result.riskAlerts.length) {
      ElMessage.warning(`风险提示：${result.riskAlerts.join('；')}`)
    }
  }
}
</script>

<style scoped>
.f2-st-25 { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.table-block { margin-top: 8px; border-top: 1px solid #ebeef5; padding-top: 12px; }
.toolbar-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.hint { font-size: 12px; color: #909399; }
:deep(.warn-row) { background: #fef0f0; }
h4 { margin: 12px 0 6px; }
</style>
