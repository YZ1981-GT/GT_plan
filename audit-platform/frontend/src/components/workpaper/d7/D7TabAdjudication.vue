<template>
<div class="d7-adjudication">
    <div class="toolbar">
      <el-button size="small" @click="exportTemplate">导出模板</el-button>
      <el-button size="small" @click="exportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button size="small" :loading="importing">导入数据</el-button>
      </el-upload>
    </div>
    <!-- 交叉验证警告 -->
    <el-alert
      v-if="crossValidationWarning"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom:12px"
    >
      {{ crossValidationWarning }}
    </el-alert>

    <!-- CAS14准则提示 -->
    <details class="editing-hints">
      <summary>📖 CAS14 合同负债vs预收账款区分决策</summary>
      <div class="hints-content">
        <p><strong>合同负债</strong>（科目2205）：已收/应收对价，应向客户转让商品的义务（CAS14适用）。</p>
        <p><strong>预收账款</strong>（科目2203）：不适用CAS14的预收款项。</p>
        <p>决策树：是否存在合同→是否已收对价→是否有履约义务→合同负债 / 预收账款。</p>
        <p>相关底稿：<GtIndexChip wp-code="D3" label="→D3 预收账款" /></p>
      </div>
    </details>

    <!-- 一、按性质分类区块 -->
    <div class="adjudication-block">
      <h4 class="block-title">一、按性质分类</h4>
      <el-table
        :data="natureRows"
        size="small"
        border
        :row-class-name="({ row }: any) => getRowClassName(row)"
        @cell-contextmenu="onCellContextMenu"
      >
        <el-table-column prop="label" label="项目" width="280" fixed>
          <template #default="{ row }">
            <span :class="{ 'label-bold': isSummaryRow(row), 'label-deduction': row.isDeductionRow }">
              {{ row.label }}
              <el-tooltip v-if="row.isFromCrossSheet" content="跨sheet自动取数（来源：D7-2明细表）" placement="top">
                <el-icon style="margin-left:4px;color:#409eff"><InfoFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初未审" width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEdit(row, 'priorUnadjusted')" :model-value="row.priorUnadjusted" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowKey, 'priorUnadjusted', v ?? 0)" />
            <span v-else :class="cellClass(row)">{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEdit(row, 'priorAje')" :model-value="row.priorAje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowKey, 'priorAje', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEdit(row, 'priorRje')" :model-value="row.priorRje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowKey, 'priorRje', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
          </template>
        </el-table-column>

        <!-- 期末 -->
        <el-table-column label="期末未审" width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEdit(row, 'currentUnadjusted')" :model-value="row.currentUnadjusted" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowKey, 'currentUnadjusted', v ?? 0)" />
            <span v-else :class="cellClass(row)">{{ fmtAmount(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEdit(row, 'currentAje')" :model-value="row.currentAje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowKey, 'currentAje', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.currentAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEdit(row, 'currentRje')" :model-value="row.currentRje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowKey, 'currentRje', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.currentRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span class="auto-calc">{{ fmtAmount(row.currentAudited) }}</span>
          </template>
        </el-table-column>

        <!-- 变动 -->
        <el-table-column label="变动额" width="115" align="right">
          <template #default="{ row }">
            <span :class="{ 'diff-red': row.changeAmount !== 0 }">{{ fmtAmount(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="85" align="center">
          <template #default="{ row }">
            <span :class="{ 'rate-exceed': isRateExceed(row.changeRate) }">{{ fmtPercent(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="140">
          <template #default="{ row }">
            <el-input v-if="row.isEditable && !isReadonly" :model-value="row.reasonAnalysis" size="small" @change="(v: string) => updateCell(row.rowKey, 'reasonAnalysis', v)" />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 二、按账龄分类区块 -->
    <div class="adjudication-block">
      <div class="block-separator" />
      <h4 class="block-title">二、按账龄分类</h4>
      <el-table
        :data="agingRows"
        size="small"
        border
        :row-class-name="({ row }: any) => getRowClassName(row)"
      >
        <el-table-column prop="label" label="项目" width="280" fixed>
          <template #default="{ row }">
            <span :class="{ 'label-bold': isSummaryRow(row) }">
              {{ row.label }}
              <el-tooltip v-if="row.isFromCrossSheet" content="跨sheet自动取数（来源：D7-2明细表）" placement="top">
                <el-icon style="margin-left:4px;color:#409eff"><InfoFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期初未审" width="115" align="right">
          <template #default="{ row }">
            <span :class="cellClass(row)">{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }"><span>{{ fmtAmount(row.priorAje) }}</span></template>
        </el-table-column>
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }"><span>{{ fmtAmount(row.priorRje) }}</span></template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="期末未审" width="115" align="right">
          <template #default="{ row }"><span :class="cellClass(row)">{{ fmtAmount(row.currentUnadjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }"><span>{{ fmtAmount(row.currentAje) }}</span></template>
        </el-table-column>
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }"><span>{{ fmtAmount(row.currentRje) }}</span></template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.currentAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="变动额" width="115" align="right">
          <template #default="{ row }">
            <span :class="{ 'diff-red': row.rowType === 'diff' && row.priorAudited !== 0 || row.currentAudited !== 0 && row.rowType === 'diff' }">{{ fmtAmount(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="85" align="center">
          <template #default="{ row }">
            <span :class="{ 'rate-exceed': isRateExceed(row.changeRate) }">{{ fmtPercent(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="140">
          <template #default="{ row }"><span>{{ row.reasonAnalysis }}</span></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- TB差异 -->
    <div class="tb-diff-section">
      <div class="tb-row">
        <span>试算平衡表数（科目2205）：</span>
        <span class="tb-amount">{{ fmtAmount(trialBalanceAmount) }}</span>
      </div>
      <div class="tb-row" :class="{ 'diff-red': trialBalanceDiff !== 0 }">
        <span>差异：</span>
        <span>{{ fmtAmount(trialBalanceDiff) }}</span>
        <span v-if="trialBalanceDiff === 0" class="check-mark"> ✓</span>
        <span v-else class="cross-mark"> ✗</span>
      </div>
    </div>

    <!-- 审计说明 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>
      <div class="note-item">
        <label>变动分析：<GtIndexChip wp-code="D7-2" label="→D7-2" /></label>
        <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="分析合同负债本期变动原因..." />
        <div class="note-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genExplanation">🤖AI</el-button>
          <el-button size="small" @click="openReview('D7-1-note-explanation')">💬复核</el-button>
        </div>
      </div>
      <div class="note-item">
        <label>账龄分析：<GtIndexChip wp-code="D7-5" label="→D7-5" /></label>
        <el-input v-model="auditNotes.agingExplanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="分析账龄超过1年合同负债的原因及合理性..." />
        <div class="note-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genAgingExplanation">🤖AI</el-button>
          <el-button size="small" @click="openReview('D7-1-note-aging-explanation')">💬复核</el-button>
        </div>
      </div>
      <div class="note-item">
        <label>CAS14区分说明：<GtIndexChip wp-code="D3" label="→D3 预收账款" /></label>
        <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="对合同负债与预收账款的区分结论..." />
        <div class="note-actions">
          <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genConclusion">🤖AI</el-button>
          <el-button size="small" @click="openReview('D7-1-note-conclusion')">💬复核</el-button>
        </div>
      </div>
    </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabAdjudication.vue — 审定表 D7-1 (~400行)
 * 双区块：按性质分类7行 + 按账龄分类7行
 * Task: 16.1
 * Requirements: 2.1-2.9, 3.4, 3.6, 4.1-4.7, 17.1-17.3, 19.1, 20.1, 21.1-21.5, 22.1-22.4
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { useD7Adjudication, type AdjudicationRow } from '../composables/useD7Adjudication'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useD7AiGenerate } from '../composables/useD7AiGenerate'
import { isChangeRateExceeding } from '../composables/useD7FormulaEngine'
import type { ChecklistResponse } from '../composables/useD7FormData'
import type useD7CrossSheet from '../composables/useD7CrossSheet'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD7CrossSheet>
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD7ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D7-1',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const {
  natureRows,
  agingRows,
  trialBalanceAmount,
  trialBalanceDiff,
  crossValidationWarning,
  auditNotes,
  updateCell,
} = useD7Adjudication({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD7AiGenerate(toRef(props, 'wpId'))

async function genExplanation() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-change-analysis', auditNotes.value.explanation, {
    task: '合同负债本期变动分析',
    trialBalanceDiff: trialBalanceDiff.value,
    crossValidationWarning: crossValidationWarning.value || '',
  }, 'AI · 变动分析')
  if (text) auditNotes.value.explanation = text
}

async function genAgingExplanation() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-aging-reason', auditNotes.value.agingExplanation, {
    task: '账龄超过1年合同负债原因分析',
  }, 'AI · 账龄分析')
  if (text) auditNotes.value.agingExplanation = text
}

async function genConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('adj-conclusion', auditNotes.value.conclusion, {
    task: 'CAS14合同负债与预收账款区分结论',
    trialBalanceAmount: trialBalanceAmount.value,
    trialBalanceDiff: trialBalanceDiff.value,
  }, 'AI · CAS14区分结论')
  if (text) auditNotes.value.conclusion = text
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateExceed(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}

function isSummaryRow(row: AdjudicationRow): boolean {
  return row.rowType === 'subtotal' || row.rowType === 'total' || row.rowType === 'tb' || row.rowType === 'diff'
}

function canEdit(row: AdjudicationRow, _field: string): boolean {
  return row.isEditable && !props.isReadonly && row.rowType !== 'subtotal' && row.rowType !== 'total'
}

function cellClass(row: AdjudicationRow): Record<string, boolean> {
  return { 'cross-sheet-cell': row.isFromCrossSheet }
}

function getRowClassName({ row }: { row: AdjudicationRow }): string {
  if (row.isDeductionRow) return 'deduction-row'
  if (row.rowType === 'total') return 'total-row'
  if (row.rowType === 'diff' && (row.priorAudited !== 0 || row.currentAudited !== 0)) return 'diff-highlight-row'
  return ''
}

function onCellContextMenu(row: AdjudicationRow, _col: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  openReviewDialog(`D7-1-adj-${row.rowKey}`)
}

function openReview(sectionId: string) {
  openReviewDialog(sectionId)
}
</script>

<style scoped>
.d7-adjudication { padding: 16px; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }

.editing-hints {
  margin-bottom: 16px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}
.editing-hints summary {
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #409eff;
}
.hints-content {
  padding: 0 14px 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}
.hints-content p { margin: 0 0 4px; }

.adjudication-block { margin-bottom: 8px; }
.block-separator { height: 2px; background: #303133; margin: 16px 0; }
.block-title { font-size: 14px; font-weight: 700; margin: 0 0 8px; color: #303133; }

.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.label-bold { font-weight: 700; }
.label-deduction { color: #409eff; }
.rate-exceed { color: #f56c6c; font-weight: 600; }
.diff-red { color: #f56c6c; font-weight: 600; }

:deep(.deduction-row) { background-color: #ecf5ff !important; }
:deep(.total-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.diff-highlight-row) { background-color: #fef0f0 !important; }

.tb-diff-section {
  margin: 16px 0;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  gap: 32px;
  font-size: 13px;
}
.tb-row { display: flex; align-items: center; gap: 4px; }
.tb-amount { font-weight: 600; }
.check-mark { color: #67c23a; }
.cross-mark { color: #f56c6c; }

.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.note-item { margin-bottom: 16px; }
.note-item label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #606266; margin-bottom: 6px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
