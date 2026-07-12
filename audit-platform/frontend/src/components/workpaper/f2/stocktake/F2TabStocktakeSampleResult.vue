<template>
  <div class="f2-st-25">
    <h3 class="title">抽盘结果汇总 F2-25</h3>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总监盘现场抽盘结果，比对账面数量与实际抽盘数量，是存货监盘抽样结论的核心底稿（CAS 1311 存货监盘）。</p>
        <p>2. 差异数量 = 抽盘数量 − 账面数量；存在差异的行自动红色高亮，须填写差异原因。</p>
        <p>3. 可点击"LLM 差异分析"由模型汇总差异并提示风险；抽盘差异率过高应扩大抽样范围或提请审计调整。</p>
        <p>4. 可通过 📎 上传盘点表，由 OCR 识别数量自动填入对应行。</p>
      </div>
    </details>

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
      <div class="tab-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">+ 新增明细行</el-button>
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
          <span class="hint">抽盘明细表（底稿 F-汇总表，保留表格）</span>
        </div>
        <div class="toolbar-right">
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
          <span class="chip-wrap"><GtIndexChip value="wp:F2-25" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ sheet.rows.value.length }} 行</el-tag>
        </div>
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
        <el-table-column label="差异数量" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="公式：抽盘数量 − 账面数量" placement="top">
              <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.varianceQty.toLocaleString() }}</span>
            </el-tooltip>
          </template>
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

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">抽盘数量与账面数量核对：</span>
      <el-tag v-if="varianceCount > 0" type="danger" size="small">{{ varianceCount }} 个品名存在差异</el-tag>
      <el-tag v-else type="success" size="small">抽盘核对一致</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">汇总结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F2-25" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <el-input v-model="sheet.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="抽盘结果汇总说明（差异原因、抽样充分性、风险提示与结论等）..." />
    </el-card>
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
import GtIndexChip from '../../GtIndexChip.vue'

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
.f2-st-25 { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-st-25 :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-st-25 :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.title { margin: 0 0 8px; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

.table-block { margin-top: 8px; border-top: 1px solid #ebeef5; padding-top: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.hint { font-size: 12px; color: #909399; }

/* 表格 */
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.formula-cell.diff-warn { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fef0f0; }

/* 核对行 */
.tb-check-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; margin: 12px 0; font-size: var(--wp-font-size, 13px); }
.tb-label { color: #909399; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
</style>
