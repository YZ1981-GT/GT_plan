<template>
  <div class="f2-st-26">
    <h3 class="title">盘点倒轧表 F2-26</h3>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表将盘点日实盘数量倒轧至资产负债表日，验证时点差异，适用于监盘日≠期末日的情形（CAS 1311 存货监盘）。</p>
        <p>2. 理论结存 = 盘点日数量 + 盘点日至期末入库 − 盘点日至期末出库；差异 = 账面结存 − 理论结存。</p>
        <p>3. 存在差异的行自动红色高亮，应追溯盘点日至期末的出入库单据核实。</p>
        <p>4. 可通过 📎 上传出入库单据，由 OCR 识别数量自动填入对应行。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证监盘日实盘数量倒轧至期末的准确性，确认期末账面结存与理论结存一致，支持存货存在性认定。"
      class="objective-alert"
    />

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
      <div class="tab-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">+ 新增明细行</el-button>
          <span class="hint">倒轧明细表（公式：理论结存 = 盘点日 + 入库 − 出库）</span>
        </div>
        <div class="toolbar-right">
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
          <span class="chip-wrap"><GtIndexChip value="wp:F2-26" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ sheet.rows.value.length }} 行</el-tag>
        </div>
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
        <el-table-column label="理论结存" width="95" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="公式：盘点日数量 + 入库 − 出库" placement="top">
              <span class="formula-cell">{{ row.theoreticalQty.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账面结存" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
              @update:model-value="(v: number) => sheet.updateRow(row.id, { bookQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="差异" width="80" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="公式：账面结存 − 理论结存" placement="top">
              <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.variance.toLocaleString() }}</span>
            </el-tooltip>
          </template>
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

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">理论结存与账面结存倒轧核对：</span>
      <el-tag v-if="varianceCount > 0" type="danger" size="small">{{ varianceCount }} 个品名存在差异</el-tag>
      <el-tag v-else type="success" size="small">倒轧核对一致</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">倒轧结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F2-26" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <el-input v-model="sheet.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="盘点倒轧说明（时点差异、出入库核实、差异结论等）..." />
    </el-card>
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
import GtIndexChip from '../../GtIndexChip.vue'

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
.f2-st-26 { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-st-26 :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-st-26 :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.title { margin: 0 0 8px; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

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
