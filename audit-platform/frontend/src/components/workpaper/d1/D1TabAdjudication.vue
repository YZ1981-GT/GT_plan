<script setup lang="ts">
/**
 * D1TabAdjudication.vue — 审定表D1-1 HTML渲染
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 8.1
 *
 * 渲染三区块 el-table（原值/坏账/净值），每区块含明细行+小计行。
 * 跨sheet自动取数浅蓝色背景 + 变动率>30%红色高亮 + 试算平衡表差异。
 * 审计说明/结论区域 + AI生成 + 复核对话入口。
 */
import { ref, computed, inject, toRef, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import {
  useD1Adjudication,
  type AdjudicationDetailRow,
  type AdjudicationSection,
} from '../composables/useD1Adjudication'
import { isChangeRateExceeding } from '../composables/useD1FormulaEngine'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import http from '@/utils/http'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../shared/WpAmountInput.vue'
import {
  D1_ADJ_REVIEW_SECTION,
  d1AdjReviewSectionId,
} from '../composables/d1AdjudicationModel'
import WpFourTableSourcePanel from '@/components/workpaper/shared/WpFourTableSourcePanel.vue'
import {
  pickDTbSourceCodes,
  normalizeDSlots,
  dCycleBasisLabel,
} from '../composables/dCycleAccountScope'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
  tbSeedAmount?: number
  /** TB 核对行取数溯源（原值 / 坏账准备 / 净额），由宿主从 render 的 project_context 派生 */
  tbSeedProvenance?: { gross: number; provision: number; net: number; hasProvision: boolean }
  /**
   * render 下发的本 sheet `html_data`（含 `tb_source_codes` / `parent_check`）。
   *
   * 🔴 必须由宿主显式传入 —— 漏传不会报错、只会让四表取数溯源恒 `undefined`
   * （Vue 对未声明的属性会静默落到根元素当 HTML 属性，`get_diagnostics`/vitest/
   * Vite transform 四层全绿），平台已登记该范式为「漏传 prop = 静默锁死」。
   */
  htmlData?: Record<string, any> | null
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const openReviewDialog = inject<((params: { sectionId: string; sectionLabel: string; relatedData?: Record<string, unknown> }) => void) | null>('openReviewDialog', null)
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-1')

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  adjudicationSections,
  crossSheetStatus,
  trialBalanceDiff,
  auditNote,
  auditConclusion,
  autoChangeDescription,
  updateCell,
  saveAuditNote,
  saveAuditConclusion,
  aiGenerateNote,
  aiGenerateConclusion,
} = useD1Adjudication({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  loadSubWorkpaperData: async () => ({}),
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  openReviewDialog: openReviewDialog ?? undefined,
  tbSeedAmount: computed(() => props.tbSeedAmount ?? 0) as Ref<number>,
})

// ─── 从集中登记带入调整（1121 应收票据，资产借方；带入期末 AJE/RJE） ─────────────
const bringInRows = computed(() => {
  const gross = adjudicationSections.value.find((s) => s.sectionKey === 'gross')
  return (gross?.rows ?? []).map((r) => ({
    rowKey: r.rowKey,
    name: r.label,
    aje: r.currentAje,
    rje: r.currentRje,
  }))
})
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1121',
  direction: 'debit',
  subjectCode: '1121',
  wpCode: 'D1',
  subjectLabel: '应收票据(1121)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'current-rje' : 'current-aje', value),
  totalAudited: () => trialBalanceDiff.value.auditedAmount,
})

// ─── Loading & Active Threads ────────────────────────────────────────────────

const loading = ref(true)
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

onMounted(() => {
  loading.value = false
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

function fmtRate(rate: number | ''): string {
  if (rate === '') return '-'
  return (rate * 100).toFixed(2) + '%'
}

function isRateExceeding(rate: number | ''): boolean {
  return isChangeRateExceeding(rate, 0.3)
}

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getAllRows(section: AdjudicationSection): AdjudicationDetailRow[] {
  return [...section.rows, section.subtotalRow]
}

function getRowClass({ row }: { row: AdjudicationDetailRow }): string {
  if (!row.isEditable) return 'is-summary'
  return ''
}

function getCellClass(row: AdjudicationDetailRow, field: string): string {
  const classes: string[] = []
  if (row.isFromCrossSheet && ['priorUnadjusted', 'currentUnadjusted'].includes(field)) {
    classes.push('cross-sheet-cell')
  }
  if (field === 'changeRate' && isRateExceeding(row.changeRate)) {
    classes.push('rate-warning')
  }
  return classes.join(' ')
}

function getCrossSheetTooltip(row: AdjudicationDetailRow): string {
  if (!row.isFromCrossSheet) return ''
  if (row.rowKey.startsWith('gross-')) return `取自D1-2 ${row.label}行`
  if (row.rowKey.startsWith('bd-')) return `取自D1-4 坏账准备${row.label}行`
  if (row.rowKey.startsWith('net-')) return '自动计算: 原值 - 坏账准备'
  return ''
}

// ─── Context Menu ────────────────────────────────────────────────────────────

function handleCellContextMenu(row: AdjudicationDetailRow, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  openReviewDialog({
    sectionId: d1AdjReviewSectionId(row.rowKey, field),
    sectionLabel: `D1-1 审定表 ${row.label} - ${column?.label || field}`,
    relatedData: { rowKey: row.rowKey, field, value: (row as any)[field] },
  })
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

async function handleAiNote() {
  aiNoteLoading.value = true
  try {
    const text = await aiGenerateNote()
    if (text) {
      saveAuditNote(text)
      ElMessage.success('AI已生成审计说明')
    }
  } catch { ElMessage.warning('AI生成失败，请重试') }
  finally { aiNoteLoading.value = false }
}

async function handleAiConclusion() {
  aiConclusionLoading.value = true
  try {
    const text = await aiGenerateConclusion()
    if (text) {
      saveAuditConclusion(text)
      ElMessage.success('AI已生成审计结论')
    }
  } catch { ElMessage.warning('AI生成失败，请重试') }
  finally { aiConclusionLoading.value = false }
}


// ─── 四表库取数溯源（Task 16）────────────────────────────────────────
// 🔴 落点两套并存：D1/D2/D3/D5/D6/D7 写 `html_data` 顶层、D4 写
// `project_context` —— `pickDTbSourceCodes` 两层都读，只读一层会恒 undefined。
const dTbSourceCodes = computed(() =>
  normalizeDSlots(pickDTbSourceCodes(props.htmlData)),
)
const dSourceHints = [
  '取数口径：<code>期末余额</code>；标准码查试算平衡表、客户原始码查余额表。',
  '「本项目无此科目」与「余额为 0」是两回事 —— 前者金额显示为空，后者显示 0.00。',
]

</script>

<template>
  <div class="d1-tab-adjudication">
    <!-- 四表库取数溯源（消 dead output：消费 render 下发的 tb_source_codes；
         口径 = {{ dCycleBasisLabel('D1') }}） -->
    <WpFourTableSourcePanel
      :source-codes="dTbSourceCodes"
      gross-label="应收票据原值"
      provision-label="坏账准备-应收票据"
      fallback-row-code="BS-005"
      :hints="dSourceHints"
    />
    <div class="tab-header">
      <h4>审定表 D1-1</h4>
      <div class="toolbar-right">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
    </div>
    <!-- Loading skeleton -->
    <el-skeleton v-if="loading" :rows="12" animated />

    <template v-else>
      <!-- 三区块审定表 -->
      <div v-for="section in adjudicationSections" :key="section.sectionKey" class="section-block">
        <h4 class="section-title">{{ section.sectionLabel }}</h4>
        <el-table
          :data="getAllRows(section)"
          border
          size="small"
          :row-class-name="getRowClass"
          @cell-contextmenu="handleCellContextMenu"
        >
          <el-table-column label="项目" prop="label" width="140" fixed>
            <template #default="{ row }">
              {{ row.label }}
              <GtReviewDot v-if="row.rowKey" row-prefix="D1-adj" :row-key="row.rowKey" />
            </template>
          </el-table-column>

          <!-- 期初 -->
          <el-table-column label="期初未审" width="110" align="right">
            <template #default="{ row }">
              <el-tooltip v-if="row.isFromCrossSheet" :content="getCrossSheetTooltip(row)" placement="top">
                <span :class="getCellClass(row, 'priorUnadjusted')" v-html="fmtAmount(row.priorUnadjusted)" />
              </el-tooltip>
              <span v-else v-html="fmtAmount(row.priorUnadjusted)" />
            </template>
          </el-table-column>
          <el-table-column label="期初AJE" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.priorAje"
                @update:model-value="(v: number) => updateCell(row.rowKey, 'prior-aje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.priorAje)" />
            </template>
          </el-table-column>
          <el-table-column label="期初RJE" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.priorRje"
                @update:model-value="(v: number) => updateCell(row.rowKey, 'prior-rje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.priorRje)" />
            </template>
          </el-table-column>
          <el-table-column label="期初审定" width="110" align="right">
            <template #default="{ row }">
              <span style="font-weight: 600" v-html="fmtAmount(row.priorAudited)" />
            </template>
          </el-table-column>

          <!-- 期末 -->
          <el-table-column label="期末未审" width="110" align="right">
            <template #default="{ row }">
              <el-tooltip v-if="row.isFromCrossSheet" :content="getCrossSheetTooltip(row)" placement="top">
                <span :class="getCellClass(row, 'currentUnadjusted')" v-html="fmtAmount(row.currentUnadjusted)" />
              </el-tooltip>
              <WpAmountInput
                v-else-if="row.isEditable && !isReadonly"
                :model-value="row.currentUnadjusted"
                @update:model-value="(v: number) => updateCell(row.rowKey, 'current-unadj', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.currentUnadjusted)" />
            </template>
          </el-table-column>
          <el-table-column label="期末AJE" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentAje"
                @update:model-value="(v: number) => updateCell(row.rowKey, 'current-aje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.currentAje)" />
            </template>
          </el-table-column>
          <el-table-column label="期末RJE" width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentRje"
                @update:model-value="(v: number) => updateCell(row.rowKey, 'current-rje', v || 0)"
              />
              <span v-else v-html="fmtAmount(row.currentRje)" />
            </template>
          </el-table-column>
          <el-table-column label="期末审定" width="110" align="right">
            <template #default="{ row }">
              <span style="font-weight: 600" v-html="fmtAmount(row.currentAudited)" />
            </template>
          </el-table-column>

          <!-- 变动 -->
          <el-table-column label="增减变动额" width="120" align="right">
            <template #default="{ row }">
              <span v-html="fmtAmount(row.change)" />
            </template>
          </el-table-column>
          <el-table-column label="增减比例" width="100" align="right">
            <template #default="{ row }">
              <span :class="{ 'rate-warning': isRateExceeding(row.changeRate) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="原因分析" min-width="140">
            <template #default="{ row }">
              <el-input
                v-if="row.isEditable && !isReadonly"
                :model-value="row.reasonAnalysis"
                size="small"
                @change="(v: string) => updateCell(row.rowKey, 'reason', v as any)"
              />
              <span v-else>{{ row.reasonAnalysis || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 试算平衡表 -->
      <div class="trial-balance-section">
        <h4 class="section-title">试算平衡表核对</h4>
        <!-- 取数溯源：源模板 E20=E18-E19 比的是「三、应收票据净值」→ TB 侧必须取净额。
             展示原值 − 坏账准备 = 净额，便于审计师追溯口径（四表库来源见下方科目）。 -->
        <div v-if="tbSeedProvenance?.hasProvision" class="tb-provenance">
          <el-tag size="small" type="info" effect="plain">取数口径：净额</el-tag>
          <span class="tb-provenance-text">
            原值 <span v-html="fmtAmount(tbSeedProvenance.gross)" />
            − 坏账准备 <span v-html="fmtAmount(tbSeedProvenance.provision)" />
            = <strong v-html="fmtAmount(tbSeedProvenance.net)" />
          </span>
        </div>
        <div class="tb-row">
          <span class="tb-label">试算平衡表数:</span>
          <!-- 🔴 可编辑金额只能用 WpAmountInput：el-input-number 的 :formatter 在
               本平台 EP 版本下不存在（千分符从不生效），见平台级数值格式铁律 -->
          <WpAmountInput
            v-if="!isReadonly"
            :model-value="trialBalanceDiff.tbAmount"
            @update:model-value="(v: number) => updateCell('tb', 'amount', v || 0)"
          />
          <span v-else v-html="fmtAmount(trialBalanceDiff.tbAmount)" />
        </div>
        <div class="tb-row">
          <span class="tb-label">审定表审定数:</span>
          <span style="font-weight: 600" v-html="fmtAmount(trialBalanceDiff.auditedAmount)" />
        </div>
        <!-- 🔴 一致性判定必须走 matched（按分容差）：浮点噪声会让 diff 显示 0.00 却打红 -->
        <div class="tb-row" :class="{ 'diff-warning': !trialBalanceDiff.matched }">
          <span class="tb-label">差异:</span>
          <span v-html="fmtAmount(trialBalanceDiff.diff)" />
          <el-tag v-if="trialBalanceDiff.matched" type="success" size="small" style="margin-left:8px">✓ 一致</el-tag>
          <el-tag v-else type="danger" size="small" style="margin-left:8px">✗ 存在差异</el-tag>
        </div>
      </div>

      <!-- 1.审计说明 -->
      <div class="audit-note-section">
        <h4 class="section-title">1.审计说明</h4>
        <p class="auto-description">{{ autoChangeDescription }}</p>
        <div class="note-area">
          <span class="red-label">主要原因（比例超过30%的）：</span>
          <div class="note-input-row">
            <el-input
              v-model="auditNote"
              type="textarea"
              :rows="3"
              :disabled="isReadonly"
              placeholder="请输入审计说明..."
              @change="saveAuditNote(auditNote)"
            />
            <div class="note-actions">
              <el-button size="small" :loading="aiNoteLoading" :disabled="isReadonly" @click="handleAiNote">🤖AI</el-button>
              <GtReviewTrigger :section-id="D1_ADJ_REVIEW_SECTION.auditNote" />
            </div>
          </div>
        </div>
      </div>

      <!-- 2.审计结论 -->
      <div class="audit-conclusion-section">
        <h4 class="section-title">2.审计结论</h4>
        <div class="note-input-row">
          <el-input
            v-model="auditConclusion"
            type="textarea"
            :rows="3"
            :disabled="isReadonly"
            placeholder="请输入审计结论..."
            @change="saveAuditConclusion(auditConclusion)"
          />
          <div class="note-actions">
            <el-button size="small" :loading="aiConclusionLoading" :disabled="isReadonly" @click="handleAiConclusion">🤖AI</el-button>
            <GtReviewTrigger :section-id="D1_ADJ_REVIEW_SECTION.auditConclusion" />
          </div>
        </div>
      </div>
    </template>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1121 应收票据"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<style scoped>
.d1-tab-adjudication {
  padding: 12px;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.section-block {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #303133;
}

/* 小计行/净值行不可编辑样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* 跨sheet自动取数单元格浅蓝色背景 */
.cross-sheet-cell {
  background-color: #ecf5ff;
  padding: 2px 4px;
  border-radius: 2px;
}

/* 变动率>30%红色高亮 */
.rate-warning {
  color: #f56c6c;
  font-weight: 600;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 试算平衡表 */
.trial-balance-section {
  margin: 20px 0;
  padding: 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.tb-provenance {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 10px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  font-size: 12px;
}

.tb-provenance-text {
  color: #606266;
  font-variant-numeric: tabular-nums;
}

.tb-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: var(--wp-font-size, 13px);
}

.tb-label {
  width: 120px;
  color: #606266;
}

.diff-warning {
  color: #f56c6c;
  font-weight: 600;
}

/* 审计说明/结论 */
.audit-note-section,
.audit-conclusion-section {
  margin: 20px 0;
  padding: 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.auto-description {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  margin: 0 0 8px 0;
}

.red-label {
  color: #f56c6c;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}

.note-area {
  margin-top: 8px;
}

.note-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 6px;
}

.note-input-row .el-textarea {
  flex: 1;
}

.note-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

</style>
