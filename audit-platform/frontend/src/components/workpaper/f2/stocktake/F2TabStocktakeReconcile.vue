<template>
  <div class="f2-st-24">
    <h3 class="title">账面余额与仓储台账核对 F2-24</h3>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表核对账面余额与仓储台账（ERP/永续盘存）数量与金额的一致性，是存货存在性与完整性认定的关键程序（CAS 1311 存货监盘）。</p>
        <p>2. 数量差异 = 账面数量 − ERP 数量；金额差异 = 账面金额 − ERP 金额；存在差异的行自动红色高亮。</p>
        <p>3. 差异应查明原因（未达账项 / 计量或记录错误 / 盘盈盘亏），评估是否需提议审计调整分录。</p>
        <p>4. 可通过 📎 上传仓储台账，由 OCR 识别数量与金额自动填入对应行。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实存货账面记录与实物仓储台账一致，验证存货存在性与计价准确性，识别账实差异并追溯原因。"
      class="objective-alert"
    />

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
      <div class="tab-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">+ 新增明细行</el-button>
          <span class="hint">明细核对表（品名级差异）</span>
        </div>
        <div class="toolbar-right">
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
          <span class="chip-wrap"><GtIndexChip value="wp:F2-24" :context-project-id="projectId" /></span>
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
        <el-table-column label="数量差异" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="公式：账面数量 − ERP数量" placement="top">
              <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.qtyDiff.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="金额差异" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="公式：账面金额 − ERP金额" placement="top">
              <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.amtDiff.toLocaleString() }}</span>
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
      <span class="tb-label">账面与仓储台账核对：</span>
      <el-tag v-if="varianceCount > 0" type="danger" size="small">{{ varianceCount }} 个品名存在差异</el-tag>
      <el-tag v-else type="success" size="small">账实核对一致</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">核对结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F2-24" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <el-input v-model="sheet.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="账面余额与仓储台账核对说明（差异原因、是否需调整分录等）..." />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, onMounted, type Ref } from 'vue'
import { useF2StocktakeRows } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeOcr } from '../../composables/useF2StocktakeOcr'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import { F2_24_NARRATIVE_FIELDS, type StocktakeReconcileRow } from './f2StocktakeConfigs'
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

// ─── 审计结论（标准打磨项，独立持久化） ───────────────────────────────────────
const CONCLUSION_KEY = 'F2-24-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item: ChecklistResponse = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<style scoped>
.f2-st-24 { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-st-24 :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-st-24 :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
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

/* 审计说明 / 审计结论卡片 */
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
