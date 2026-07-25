<template>
<div class="d7-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表反映合同负债（科目2205）的审定过程，依据 CAS14 收入准则，指企业已收或应收客户对价而应向客户转让商品的义务。</p>
        <p>2. "期末未审"及跨sheet浅蓝背景单元格取自 D7-2 明细表按性质/账龄聚合，不可手工编辑；灰色底纹列为自动计算的审定数。</p>
        <p>3. 合同负债（2205）与不适用 CAS14 的预收账款（2203）需严格区分，判断路径：是否存在合同→是否已收对价→是否有履约义务。</p>
        <p>4. 变动率超过30%的项目请在审计说明中解释原因；账龄超1年的合同负债应关注未结转合理性；审定完成后须与试算平衡表核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认合同负债期末余额的存在、完整与准确，评价其与预收账款分类的恰当性及与履约义务的对应关系，并与试算平衡表核对一致。"
      class="objective-alert"
    />

    <!-- 交叉验证警告 -->
    <el-alert
      v-if="crossValidationWarning"
      type="warning"
      :closable="false"
      show-icon
      class="cross-warning"
    >
      {{ crossValidationWarning }}
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" :disabled="isReadonly" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" :disabled="isReadonly">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D7-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:D3" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ natureRows.length + agingRows.length }} 行</el-tag>
      </div>
    </div>

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
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
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
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
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
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
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
        <el-table-column label="审定" width="120" align="right" class-name="auto-calc-col">
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

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（科目2205）：</span>
      <span>{{ fmtAmount(trialBalanceAmount) }}</span>
      <el-tag v-if="trialBalanceDiff !== 0" type="danger" size="small" class="diff-tag">差异 {{ fmtAmount(trialBalanceDiff) }}</el-tag>
      <el-tag v-else type="success" size="small" class="diff-tag">核对一致</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" />
            <GtIndexChip value="wp:D7-5" :context-project-id="projectId" />
            <GtIndexChip value="wp:D3" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 变动分析</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genExplanation">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D7-1-note-explanation')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="分析合同负债本期变动原因..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 账龄分析</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genAgingExplanation">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D7-1-note-aging-explanation')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.agingExplanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="分析账龄超过1年合同负债的原因及合理性..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">3. CAS14区分结论</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D7-1-note-conclusion')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="对合同负债与预收账款的区分结论..."
        />
      </div>
    </el-card>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2205 合同负债"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
</div>
</template>

<script setup lang="ts">
/**
 * D7TabAdjudication.vue — 审定表 D7-1 (~400行)
 * 双区块：按性质分类7行 + 按账龄分类7行
 * Task: 16.1
 * Requirements: 2.1-2.9, 3.4, 3.6, 4.1-4.7, 17.1-17.3, 19.1, 20.1, 21.1-21.5, 22.1-22.4
 */
import { computed, inject, toRef, ref, type Ref } from 'vue'
import { InfoFilled, Download } from '@element-plus/icons-vue'
import { useD7Adjudication, type AdjudicationRow } from '../composables/useD7Adjudication'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useD7AiGenerate } from '../composables/useD7AiGenerate'
import { isChangeRateExceeding } from '../composables/useD7FormulaEngine'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import type { ChecklistResponse } from '../composables/useD7FormData'
import type useD7CrossSheet from '../composables/useD7CrossSheet'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD7CrossSheet>
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
// TB 预填种子（科目2205期末审定，来自主入口 project_context.tb_amount）
const d7TbAmount = inject<Ref<number>>('d7TbAmount', ref(0))
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
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  tbSeedAmount: d7TbAmount,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD7AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

// ─── 从集中登记带入调整（2205 合同负债，负债贷方；带入按性质分类行期末 AJE/RJE） ─
const bringInRows = computed(() =>
  natureRows.value
    .filter(r => r.rowType === 'detail' && r.isEditable)
    .map(r => ({ rowKey: r.rowKey, name: r.label, aje: r.currentAje, rje: r.currentRje })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2205',
  direction: 'credit',
  subjectCode: '2205',
  wpCode: 'D7',
  subjectLabel: '合同负债(2205)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'currentRje' : 'currentAje', value),
  totalAudited: () => natureRows.value.find(r => r.rowKey === 'contract-liability-total')?.currentAudited ?? 0,
})

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

function getRowClassName(row: AdjudicationRow): string {
  if (!row) return ''
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
.d7-adjudication { padding: 12px; }
.d7-adjudication :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d7-adjudication :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.cross-warning { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.adjudication-block { margin-bottom: 8px; }
.block-separator { height: 2px; background: #303133; margin: 16px 0; }
.block-title { font-size: 14px; font-weight: 700; margin: 0 0 8px; color: #303133; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.label-bold { font-weight: 700; }
.label-deduction { color: #409eff; }
.rate-exceed { color: #f56c6c; font-weight: 600; }
.diff-red { color: #f56c6c; font-weight: 600; }

:deep(.deduction-row) { background-color: #ecf5ff !important; }
:deep(.total-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.diff-highlight-row) { background-color: #fef0f0 !important; }

/* 核对行 */
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin: 16px 0;
  font-size: var(--wp-font-size, 13px);
}
.tb-label { color: #909399; }
.diff-tag { margin-left: 8px; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
