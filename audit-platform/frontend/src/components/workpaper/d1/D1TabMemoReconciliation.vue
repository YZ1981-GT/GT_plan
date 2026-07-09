<script setup lang="ts">
/**
 * D1TabMemoReconciliation.vue — 备查簿核对D1-7 HTML渲染
 *
 * 卡片视图 / 宽表视图 + 联动计算 + AI辅助 + D1-2/D1-8勾稽
 */
import { ref, inject, toRef, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD1MemoReconciliation, type MemoRow } from '../composables/useD1MemoReconciliation'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import D1MemoNoteCard from './D1MemoNoteCard.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import { useWorkpaperWideTable } from '../composables/useWorkpaperWideTable'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话（Task 19 预留）：仅当 provider 存在时展示 💬 按钮
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  cutoffDate,
  bankRows,
  commercialRows,
  bankSubtotal,
  commercialSubtotal,
  grandTotal,
  reconciliationRows,
  hasDifference,
  endorsedStats,
  unexpiredSummaryRows,
  allDataRows,
  rowWarnings,
  warningCount,
  crossSheetStatus,
  auditProcedures,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  setCutoffDate,
  saveAuditProcedures,
  saveAuditNote,
  saveAuditConclusion,
} = useD1MemoReconciliation({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── Dropdown Options ─────────────────────────────────────────────────────────

const NOTE_TYPE_OPTIONS = ['银行承兑汇票', '商业承兑汇票']
const STATUS_OPTIONS = ['持有', '已贴现', '已背书', '到期']
const YN_OPTIONS = ['是', '否']
const RATING_OPTIONS = ['AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', '其他']
const RELATED_OPTIONS = ['关联方', '非关联方']

const AUDIT_OBJECTIVES = [
  '逐笔登记应收票据收到、背书、贴现、到期等全生命周期事项，确保可追溯；',
  '备查簿汇总数与明细账 D1-2 核对，差异查明原因；',
  '统计贴现/背书及未到期事项，支撑 D1-6 业务模式与 D1-8 检查。',
]

// ─── 双视图 + AI ─────────────────────────────────────────────────────────────
const viewMode = ref<'card' | 'table'>('table')
const viewModeOptions = [
  { label: '卡片视图', value: 'card' as const },
  { label: '宽表视图', value: 'table' as const },
]
const activeTab = ref('')
const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-7')
const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingProcedures = ref(false)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)
const memoOcrExtracted = ref<Map<string, Record<string, any>>>(new Map())

const warningsByRowId = computed(() => {
  const map = new Map<string, string[]>()
  for (const w of rowWarnings.value) map.set(w.rowId, w.messages)
  return map
})

function buildMemoAiContext(extra = ''): Record<string, unknown> {
  const gt = grandTotal.value
  return {
    sheet: 'D1-7',
    cutoffDate: cutoffDate.value,
    rowCount: allDataRows.value.length,
    warningCount: warningCount.value,
    hasDifference: hasDifference.value,
    reconciliation: reconciliationRows.value.map((r) => r.label).join(' / '),
    endingBalance: gt.endingBalance,
    discountedTotal: endorsedStats.value.discountedTotal,
    endorsedTotal: endorsedStats.value.endorsedTotal,
    guidance: extra,
  }
}

async function generateProceduresWithAI() {
  if (props.isReadonly) return
  aiLoadingProcedures.value = true
  try {
    const text = await generateAndConfirm(
      'memo-audit-note',
      auditProcedures.value,
      buildMemoAiContext('生成D1-7审计过程步骤清单，覆盖备查簿登记、D1-2核对、贴现背书统计、未到期汇总。'),
      'AI · 审计过程',
    )
    if (text) saveAuditProcedures(text)
  } finally {
    aiLoadingProcedures.value = false
  }
}

async function generateNoteWithAI() {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'memo-audit-note',
      auditNote.value,
      buildMemoAiContext(`审计过程：${auditProcedures.value || '未填写'}`),
      'AI · 审计说明',
    )
    if (text) saveAuditNote(text)
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateConclusionWithAI() {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'memo-audit-conclusion',
      auditConclusion.value,
      buildMemoAiContext(`审计说明：${auditNote.value || '未填写'}；差异：${hasDifference.value ? '存在' : '无'}`),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

function cardTabLabel(row: MemoRow): string {
  const no = row.noteNumber?.trim()
  if (no) return no.length > 14 ? `${no.slice(0, 14)}…` : no
  return row.category === 'bank' ? '银行承兑（新）' : '商业承兑（新）'
}

function onCardUpdate(rowId: string, field: keyof MemoRow, value: string | number) {
  updateCell(rowId, field as string, value)
}

function mapD4OcrToMemoFields(extracted: Record<string, any>, current: MemoRow): Partial<MemoRow> {
  const patch: Partial<MemoRow> = {}
  const noteNo = String(extracted.contractNo || '').trim()
  const issuer = String(extracted.counterparty || '').trim()
  const issueDate = String(extracted.signDate || '').trim()
  const maturityDate = String(extracted.settlementTime || '').trim()
  const amount = Number(extracted.contractAmount || 0)
  const remark = String(extracted.specialTerms || extracted.serviceContent || '').trim()

  if (noteNo) patch.noteNumber = noteNo
  if (issuer) patch.issuer = issuer
  if (issueDate) patch.issueDate = issueDate
  if (maturityDate) patch.maturityDate = maturityDate
  if (amount > 0) patch.amount = amount
  if (remark) patch.remarkText = current.remarkText ? `${current.remarkText}\nOCR:${remark}` : `OCR:${remark}`
  return patch
}

async function onCardUploadOcr(row: MemoRow, file: File) {
  if (props.isReadonly) return
  updateCell(row.rowId, 'ocrStatus', 'processing')
  updateCell(row.rowId, 'attachmentName', file.name)
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data ?? {}
    const extracted = (data.extracted_fields || {}) as Record<string, any>
    memoOcrExtracted.value.set(row.rowId, extracted)
    updateCell(row.rowId, 'attachmentId', String(data.attachment_id || ''))
    updateCell(row.rowId, 'attachmentName', file.name)
    updateCell(row.rowId, 'ocrStatus', 'done')
    ElMessage.success('OCR识别完成，请选择回填空字段或覆盖回填')
  } catch {
    updateCell(row.rowId, 'ocrStatus', 'failed')
    ElMessage.warning('OCR识别失败，请稍后重试')
  }
}

async function onCardApplyOcr(row: MemoRow, mode: 'empty-only' | 'override-all') {
  if (props.isReadonly) return
  const extracted = memoOcrExtracted.value.get(row.rowId)
  if (!extracted) {
    ElMessage.info('暂无OCR结果，请先上传附件')
    return
  }
  if (mode === 'override-all') {
    try {
      await ElMessageBox.confirm('将使用OCR结果覆盖当前可映射字段，是否继续？', '覆盖回填确认', {
        type: 'warning',
        confirmButtonText: '继续覆盖',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
  }
  const patch = mapD4OcrToMemoFields(extracted, row)
  let count = 0
  ;(Object.keys(patch) as Array<keyof MemoRow>).forEach((k) => {
    const nextVal = patch[k] as any
    const currentVal = (row as any)[k]
    if (mode === 'empty-only' && currentVal) return
    if (nextVal === undefined || nextVal === null || nextVal === '') return
    updateCell(row.rowId, k, nextVal)
    count++
  })
  ElMessage.success(count > 0 ? `已回填 ${count} 个字段` : '无可回填字段')
}

function onCardRemoveAttachment(row: MemoRow) {
  if (props.isReadonly) return
  updateCell(row.rowId, 'attachmentId', '')
  updateCell(row.rowId, 'attachmentName', '')
  updateCell(row.rowId, 'ocrStatus', 'none')
  memoOcrExtracted.value.delete(row.rowId)
}

watch(allDataRows, (rows) => {
  if (!activeTab.value && rows.length > 0) activeTab.value = rows[0].rowId
  if (activeTab.value && !rows.some((r) => r.rowId === activeTab.value) && rows.length > 0) {
    activeTab.value = rows[0].rowId
  }
}, { immediate: true })

// ─── Column Descriptors ───────────────────────────────────────────────────────

type ColType = 'text' | 'number' | 'date' | 'select'
interface ColDesc {
  field: keyof MemoRow
  label: string
  width: number
  type: ColType
  options?: string[]
  readonly?: boolean
}

// 基本信息（剩余 6 列；票据类型/票据号 fixed left 单列，见 template）
const basicCols: ColDesc[] = [
  { field: 'receivedDate', label: '收到日期', width: 140, type: 'date' },
  { field: 'endorser', label: '前手', width: 120, type: 'text' },
  { field: 'issueDate', label: '出票日', width: 140, type: 'date' },
  { field: 'issuer', label: '出票人', width: 120, type: 'text' },
  { field: 'acceptor', label: '承兑人', width: 120, type: 'text' },
  { field: 'amount', label: '金额', width: 120, type: 'number' },
]

// 流转（6 列）
const flowCols: ColDesc[] = [
  { field: 'maturityDate', label: '到期日', width: 140, type: 'date' },
  { field: 'transferDate', label: '流转日', width: 140, type: 'date' },
  { field: 'status', label: '状态', width: 110, type: 'select', options: STATUS_OPTIONS },
  { field: 'endorsee', label: '被背书人', width: 120, type: 'text' },
  { field: 'discountBank', label: '贴现银行', width: 120, type: 'text' },
  { field: 'discountInterest', label: '贴现息', width: 110, type: 'number' },
]

// 金额（9 列）
const amountCols: ColDesc[] = [
  { field: 'isPledged', label: '是否质押', width: 100, type: 'select', options: YN_OPTIONS },
  { field: 'isDiscountedEndorsed', label: '审计日已贴现背书', width: 140, type: 'select', options: YN_OPTIONS },
  { field: 'beginningBalance', label: '年初余额', width: 120, type: 'number' },
  { field: 'currentReceived', label: '本期收到', width: 120, type: 'number' },
  { field: 'currentEndorsed', label: '本期背书', width: 120, type: 'number' },
  { field: 'currentMatured', label: '本期到期承兑', width: 130, type: 'number' },
  { field: 'currentDiscounted', label: '本期贴现', width: 120, type: 'number' },
  { field: 'endingBalance', label: '年末余额（自动）', width: 130, type: 'number', readonly: true },
  { field: 'unexpiredEndorsedDiscounted', label: '期末未到期背书贴现（自动）', width: 170, type: 'number', readonly: true },
]

// 审定（8 列）
const auditCols: ColDesc[] = [
  { field: 'isDerecognized', label: '是否终止确认', width: 120, type: 'select', options: YN_OPTIONS },
  { field: 'creditRating', label: '信用评级', width: 110, type: 'select', options: RATING_OPTIONS },
  { field: 'auditedFinancing', label: '审定应收款项融资', width: 150, type: 'number' },
  { field: 'auditedNotes', label: '审定应收票据', width: 130, type: 'number' },
  { field: 'relatedParty', label: '关联关系', width: 120, type: 'select', options: RELATED_OPTIONS },
  { field: 'isOverdue', label: '是否逾期', width: 100, type: 'select', options: YN_OPTIONS },
  { field: 'overdueTransferAmount', label: '逾期转应收金额', width: 140, type: 'number' },
  { field: 'remarkText', label: '备注', width: 160, type: 'text' },
]

// ─── Combined Table Data ──────────────────────────────────────────────────────

const tableData = computed<MemoRow[]>(() => [
  ...bankRows.value,
  bankSubtotal.value,
  ...commercialRows.value,
  commercialSubtotal.value,
  grandTotal.value,
])

const dataRowCount = computed(() => bankRows.value.length + commercialRows.value.length)
const browseRows = computed(() => tableData.value.filter(r => r.rowType !== 'summary'))
const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('noteType', '票据类型', 130),
  virtualTextCol('noteNumber', '票据号', 170),
  virtualTextCol('endorser', '前手', 120),
  virtualNumCol('amount', '金额', 120, displayPrefs.fmtAmount),
  virtualTextCol('status', '状态', 110),
  virtualNumCol('endingBalance', '年末余额', 120, displayPrefs.fmtAmount),
  virtualNumCol('auditedNotes', '审定应收票据', 130, displayPrefs.fmtAmount),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 1400,
})

const columnCount = ref(31)
const { useLargeTable, tableMaxHeight, wrapperStyle, minTableWidth } = useWorkpaperWideTable({
  rowCount: dataRowCount,
  columnCount,
})

function getRowClass({ row }: { row: MemoRow }): string {
  return row.rowType === 'summary' ? 'is-summary' : ''
}

// summary 行不可编辑；只读时全不可编辑
function isEditable(row: MemoRow): boolean {
  return !props.isReadonly && row.rowType !== 'summary'
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Change Handlers ───────────────────────────────────────────────────────────

function onNumberChange(rowId: string, field: keyof MemoRow, v: number | undefined) {
  updateCell(rowId, field as string, v || 0)
}

function onTextChange(rowId: string, field: keyof MemoRow, v: string) {
  updateCell(rowId, field as string, v || '')
}

// ─── Reconciliation Area Helpers ───────────────────────────────────────────────

const reconCols: Array<{ field: keyof MemoRow; label: string }> = [
  { field: 'beginningBalance', label: '年初余额' },
  { field: 'currentReceived', label: '本期收到' },
  { field: 'currentEndorsed', label: '本期背书' },
  { field: 'currentMatured', label: '本期到期' },
  { field: 'currentDiscounted', label: '本期贴现' },
  { field: 'endingBalance', label: '期末余额' },
]

function reconValue(rowIndex: number, field: keyof MemoRow): number {
  const row = reconciliationRows.value[rowIndex] as any
  return (row?.[field] as number) ?? 0
}

// 明细账行（index 1）取数失败时占位
const ledgerError = computed(() => crossSheetStatus.value === 'error')

// ─── Import/Export ───────────────────────────────────────────────────────────
// (moved to view mode section above)

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// 表格单元格右键 → 发起复核对话（Task 19.1 scaffolding）
function onCellContextMenu(row: MemoRow, _column: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  if (openReviewDialog) openReviewDialog({ sectionId: 'D1-memo-cell', rowId: row.rowId })
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  '卡片视图按单张票据纵向分组填写；宽表视图适合批量录入与 Excel 导入导出对齐。',
  '联动规则：状态→贴现/背书金额、承兑人→信用评级、截止日期→逾期/未到期汇总、年末余额自动滚动计算。',
  '备查簿应逐笔登记：对每一张银行承兑汇票、商业承兑汇票的收到、背书转让、贴现、到期承兑、退票等全生命周期事项逐笔登记，确保票据流转全过程可追溯。',
  '与明细账（D1-2）核对：备查簿逐笔登记的年初余额、本期收到、本期背书、本期到期、本期贴现、期末余额等汇总数，应与原值明细表 D1-2 相应科目一致；如存在差异应查明原因并在审计说明中记录。',
  '截止日期用于判断票据的期后事项（背书/贴现/到期）是否已终止确认；请填写审计基准日（通常为资产负债表日），据此计算"期末未到期背书贴现"及贴现背书统计。',
  '贴现/背书统计：系统按票据状态自动汇总"已贴现总额"与"已背书总额"；D1-8 可从本表按状态导入贴现/背书明细。',
]
</script>

<template>
  <div class="d1-tab-memo-reconciliation">
      <div class="tab-header">
        <h4>备查簿核对 D1-7</h4>
        <GtReviewTrigger section-id="D1-memo-header" />
      </div>
      <!-- 审计目标与过程 -->
      <details class="methodology-collapse" open>
        <summary class="methodology-summary">📖 审计目标与审计过程（点击展开/收起）</summary>
        <div class="methodology-body">
          <p class="method-title"><strong>一、审计目标：</strong></p>
          <ol class="method-objectives">
            <li v-for="(item, i) in AUDIT_OBJECTIVES" :key="'obj-' + i">{{ item }}</li>
          </ol>
          <div class="method-title-row">
            <p class="method-title"><strong>二、审计过程：</strong></p>
            <el-tooltip :content="aiAvailable ? 'AI辅助生成审计过程' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingProcedures"
                :disabled="isReadonly || !aiAvailable"
                @click="generateProceduresWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
          </div>
          <el-input
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            :model-value="auditProcedures"
            placeholder="逐笔登记 → 与D1-2核对 → 统计贴现背书 → 判断终止确认……"
            :disabled="isReadonly"
            @input="(v: string) => saveAuditProcedures(v)"
          />
        </div>
      </details>

      <!-- 截止日期 -->
      <div class="cutoff-row">
        <span class="cutoff-label">截止日期：</span>
        <el-date-picker
          :model-value="cutoffDate"
          type="date"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          placeholder="选择审计基准日"
          size="small"
          :disabled="isReadonly"
          @change="(v: string) => setCutoffDate(v || '')"
        />
      </div>

      <!-- Toolbar -->
      <div class="table-toolbar">
        <el-segmented v-model="viewMode" :options="viewModeOptions" size="small" />
        <el-button-group size="small">
          <el-button @click="onExportTemplate">导出模板</el-button>
          <el-button @click="onExportData">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx"
            :before-upload="onImportFile"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
        <el-button-group>
          <el-button size="small" :disabled="isReadonly" @click="addRow('bank')">
            + 银行承兑
          </el-button>
          <el-button size="small" :disabled="isReadonly" @click="addRow('commercial')">
            + 商业承兑
          </el-button>
        </el-button-group>
        <div class="toolbar-chips">
          <GtIndexChip value="wp:D1-2" :context-project-id="projectId" />
          <GtIndexChip value="wp:D1-8" :context-project-id="projectId" />
          <GtIndexChip value="wp:D1-6" :context-project-id="projectId" />
        </div>
      </div>

      <el-alert
        v-if="warningCount > 0"
        type="warning"
        :closable="false"
        show-icon
        class="warn-banner"
        :title="`发现 ${warningCount} 条票据需关注（缺票据号、逾期持有、贴现背书标记不一致等）`"
      />

      <!-- 卡片视图 -->
      <template v-if="viewMode === 'card'">
        <div class="overview-panel">
          <div class="overview-info">
            <h3 class="overview-title">
              备查簿核对
              <el-tag size="small" effect="plain" class="overview-code">D1-7</el-tag>
            </h3>
            <p class="overview-desc">
              共 <strong>{{ allDataRows.length }}</strong> 张票据，
              已贴现 <strong>{{ endorsedStats.discountedTotal.toLocaleString() }}</strong>，
              已背书 <strong>{{ endorsedStats.endorsedTotal.toLocaleString() }}</strong>
              <el-tag v-if="hasDifference" type="danger" size="small" style="margin-left:8px">与D1-2有差异</el-tag>
            </p>
          </div>
        </div>
        <div v-if="allDataRows.length === 0" class="empty-state">
          暂无票据记录，请点击「+ 银行承兑」或「+ 商业承兑」添加，或导入 Excel 数据。
        </div>
        <el-tabs
          v-else
          v-model="activeTab"
          type="card"
          @tab-change="() => {}"
        >
          <el-tab-pane
            v-for="row in allDataRows"
            :key="row.rowId"
            :name="row.rowId"
            :label="cardTabLabel(row)"
          >
            <D1MemoNoteCard
              :row="row"
              :warnings="warningsByRowId.get(row.rowId) || []"
              :is-readonly="isReadonly"
              :project-id="projectId"
              :note-type-options="NOTE_TYPE_OPTIONS"
              :status-options="STATUS_OPTIONS"
              :yn-options="YN_OPTIONS"
              :rating-options="RATING_OPTIONS"
              :related-options="RELATED_OPTIONS"
              @update="(field, value) => onCardUpdate(row.rowId, field, value)"
              @remove="removeRow(row.rowId)"
              @upload-ocr="(file) => onCardUploadOcr(row, file)"
              @apply-ocr="(mode) => onCardApplyOcr(row, mode)"
              @remove-attachment="onCardRemoveAttachment(row)"
            />
          </el-tab-pane>
        </el-tabs>
      </template>

      <!-- 宽表视图 -->
      <template v-else>
      <el-alert v-if="useLargeTable && !useVirtualScroll" type="info" :closable="false" show-icon class="large-table-hint">
        行数较多，已启用固定高度滚动浏览（{{ dataRowCount }} 行）
      </el-alert>
      <div v-if="useVirtualScroll" class="virtual-toolbar">
        <el-alert type="info" :closable="false" class="virtual-hint">
          行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
        </el-alert>
        <el-button size="small" @click="toggleBrowseMode">
          {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
        </el-button>
      </div>
      <el-table-v2
        v-if="useVirtualScroll && browseMode"
        :columns="virtualColumns"
        :data="browseRows"
        :width="tableWidth"
        :height="tableHeight"
        :row-height="36"
        :header-height="40"
        :row-event-handlers="rowEventHandlers"
        fixed
        class="virtual-table"
      />
      <div v-if="!useVirtualScroll || !browseMode" :style="wrapperStyle">
        <el-table
          :data="tableData"
          border
          size="small"
          :row-class-name="getRowClass"
          class="memo-table"
          :max-height="tableMaxHeight"
          :style="{ minWidth: minTableWidth }"
          @cell-contextmenu="onCellContextMenu"
        >
        <!-- 票据类型（fixed left） -->
        <el-table-column label="票据类型" width="130" fixed="left">
          <template #default="{ row }: { row: MemoRow }">
            <template v-if="row.rowType === 'summary'">
              <span class="summary-label">{{ row.noteType }}</span>
            </template>
            <el-select
              v-else-if="isEditable(row)"
              :model-value="row.noteType"
              size="small"
              placeholder="类型"
              style="width: 100%"
              @change="(v: string) => onTextChange(row.rowId, 'noteType', v)"
            >
              <el-option v-for="o in NOTE_TYPE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.noteType }}</span>
            <GtReviewDot v-if="row.rowType !== 'summary'" row-prefix="D1-memo" :row-key="row.rowId" />
          </template>
        </el-table-column>

        <!-- 票据号（fixed left，含删除按钮） -->
        <el-table-column label="票据号" width="170" fixed="left">
          <template #default="{ row }: { row: MemoRow }">
            <div v-if="row.rowType === 'summary'" class="summary-blank" />
            <div v-else class="note-number-cell">
              <el-input
                :model-value="row.noteNumber"
                size="small"
                placeholder="票据号"
                :disabled="!isEditable(row)"
                @change="(v: string) => onTextChange(row.rowId, 'noteNumber', v)"
              />
              <el-button
                v-if="row.rowType === 'dynamic' && !isReadonly"
                type="danger"
                size="small"
                text
                class="delete-btn"
                @click="removeRow(row.rowId)"
              >
                ✕
              </el-button>
            </div>
          </template>
        </el-table-column>

        <!-- 基本信息组 -->
        <el-table-column label="基本信息">
          <el-table-column
            v-for="col in basicCols"
            :key="col.field"
            :label="col.label"
            :width="col.width"
            :align="col.type === 'number' ? 'right' : 'left'"
          >
            <template #default="{ row }: { row: MemoRow }">
              <!-- summary 行 -->
              <template v-if="row.rowType === 'summary'">
                <span v-if="col.type === 'number'" class="summary-val" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else />
              </template>
              <!-- 可编辑 -->
              <template v-else-if="isEditable(row)">
                <span
                  v-if="col.type === 'number' && col.readonly"
                  class="auto-calc-val"
                  v-html="fmtAmount(row[col.field] as number)"
                />
                <el-input-number
                  v-else-if="col.type === 'number'"
                  :model-value="row[col.field] as number"
                  size="small"
                  :controls="false"
                  :precision="2"
                  @change="(v: number) => onNumberChange(row.rowId, col.field, v)"
                />
                <el-date-picker
                  v-else-if="col.type === 'date'"
                  :model-value="row[col.field] as string"
                  type="date"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  size="small"
                  style="width: 100%"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                />
                <el-select
                  v-else-if="col.type === 'select'"
                  :model-value="row[col.field] as string"
                  size="small"
                  clearable
                  style="width: 100%"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                >
                  <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                </el-select>
                <el-input
                  v-else
                  :model-value="row[col.field] as string"
                  size="small"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                />
              </template>
              <!-- 只读 -->
              <template v-else>
                <span v-if="col.type === 'number'" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else>{{ row[col.field] }}</span>
              </template>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 流转组 -->
        <el-table-column label="流转">
          <el-table-column
            v-for="col in flowCols"
            :key="col.field"
            :label="col.label"
            :width="col.width"
            :align="col.type === 'number' ? 'right' : 'left'"
          >
            <template #default="{ row }: { row: MemoRow }">
              <template v-if="row.rowType === 'summary'">
                <span v-if="col.type === 'number'" class="summary-val" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else />
              </template>
              <template v-else-if="isEditable(row)">
                <span
                  v-if="col.type === 'number' && col.readonly"
                  class="auto-calc-val"
                  v-html="fmtAmount(row[col.field] as number)"
                />
                <el-input-number
                  v-else-if="col.type === 'number'"
                  :model-value="row[col.field] as number"
                  size="small"
                  :controls="false"
                  :precision="2"
                  @change="(v: number) => onNumberChange(row.rowId, col.field, v)"
                />
                <el-date-picker
                  v-else-if="col.type === 'date'"
                  :model-value="row[col.field] as string"
                  type="date"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  size="small"
                  style="width: 100%"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                />
                <el-select
                  v-else-if="col.type === 'select'"
                  :model-value="row[col.field] as string"
                  size="small"
                  clearable
                  style="width: 100%"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                >
                  <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                </el-select>
                <el-input
                  v-else
                  :model-value="row[col.field] as string"
                  size="small"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                />
              </template>
              <template v-else>
                <span v-if="col.type === 'number'" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else>{{ row[col.field] }}</span>
              </template>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 金额组 -->
        <el-table-column label="金额">
          <el-table-column
            v-for="col in amountCols"
            :key="col.field"
            :label="col.label"
            :width="col.width"
            :align="col.type === 'number' ? 'right' : 'left'"
          >
            <template #default="{ row }: { row: MemoRow }">
              <template v-if="row.rowType === 'summary'">
                <span v-if="col.type === 'number'" class="summary-val" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else />
              </template>
              <template v-else-if="isEditable(row)">
                <span
                  v-if="col.type === 'number' && col.readonly"
                  class="auto-calc-val"
                  v-html="fmtAmount(row[col.field] as number)"
                />
                <el-input-number
                  v-else-if="col.type === 'number'"
                  :model-value="row[col.field] as number"
                  size="small"
                  :controls="false"
                  :precision="2"
                  @change="(v: number) => onNumberChange(row.rowId, col.field, v)"
                />
                <el-select
                  v-else-if="col.type === 'select'"
                  :model-value="row[col.field] as string"
                  size="small"
                  clearable
                  style="width: 100%"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                >
                  <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                </el-select>
                <el-input
                  v-else
                  :model-value="row[col.field] as string"
                  size="small"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                />
              </template>
              <template v-else>
                <span v-if="col.type === 'number'" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else>{{ row[col.field] }}</span>
              </template>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 审定组 -->
        <el-table-column label="审定">
          <el-table-column
            v-for="col in auditCols"
            :key="col.field"
            :label="col.label"
            :width="col.width"
            :align="col.type === 'number' ? 'right' : 'left'"
          >
            <template #default="{ row }: { row: MemoRow }">
              <template v-if="row.rowType === 'summary'">
                <span v-if="col.type === 'number'" class="summary-val" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else />
              </template>
              <template v-else-if="isEditable(row)">
                <span
                  v-if="col.type === 'number' && col.readonly"
                  class="auto-calc-val"
                  v-html="fmtAmount(row[col.field] as number)"
                />
                <el-input-number
                  v-else-if="col.type === 'number'"
                  :model-value="row[col.field] as number"
                  size="small"
                  :controls="false"
                  :precision="2"
                  @change="(v: number) => onNumberChange(row.rowId, col.field, v)"
                />
                <el-select
                  v-else-if="col.type === 'select'"
                  :model-value="row[col.field] as string"
                  size="small"
                  clearable
                  style="width: 100%"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                >
                  <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                </el-select>
                <el-input
                  v-else
                  :model-value="row[col.field] as string"
                  size="small"
                  @change="(v: string) => onTextChange(row.rowId, col.field, v)"
                />
              </template>
              <template v-else>
                <span v-if="col.type === 'number'" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else>{{ row[col.field] }}</span>
              </template>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      </div>
      </template>

      <!-- 核对区 -->
      <div class="section-title">核对区（备查簿 ↔ 明细账D1-2）</div>
      <table class="recon-table">
        <thead>
          <tr>
            <th class="recon-label-col">项目</th>
            <th v-for="c in reconCols" :key="c.field">{{ c.label }}</th>
          </tr>
        </thead>
        <tbody>
          <!-- 备查簿合计 (index 0) -->
          <tr>
            <td class="recon-label-col">备查簿合计</td>
            <td v-for="c in reconCols" :key="c.field" class="recon-num" v-html="fmtAmount(reconValue(0, c.field))" />
          </tr>
          <!-- 明细账 D1-2 (index 1) -->
          <tr>
            <td class="recon-label-col ledger-cell">
              <el-tooltip content="取自原值明细表D1-2" placement="top">
                <span>明细账(D1-2)</span>
              </el-tooltip>
            </td>
            <td v-for="c in reconCols" :key="c.field" class="recon-num ledger-cell">
              <template v-if="ledgerError">
                <el-tooltip content="D1-2数据不可用" placement="top">
                  <span class="ledger-warn">- ⚠️</span>
                </el-tooltip>
              </template>
              <span v-else v-html="fmtAmount(reconValue(1, c.field))" />
            </td>
          </tr>
          <!-- 差异 (index 2) -->
          <tr>
            <td class="recon-label-col">差异</td>
            <td
              v-for="c in reconCols"
              :key="c.field"
              class="recon-num"
              :class="{ 'diff-nonzero': hasDifference && reconValue(2, c.field) !== 0 }"
              v-html="fmtAmount(reconValue(2, c.field))"
            />
          </tr>
        </tbody>
      </table>
      <div v-if="hasDifference" class="diff-hint">⚠️ 备查簿合计与明细账D1-2存在差异，请查明原因并在审计说明中记录。</div>

      <!-- 贴现背书统计区 -->
      <div class="section-title">贴现背书统计</div>
      <el-descriptions :column="2" border size="small" class="endorsed-stats">
        <el-descriptions-item label="已贴现总额">
          <span v-html="fmtAmount(endorsedStats.discountedTotal)" />
        </el-descriptions-item>
        <el-descriptions-item label="已背书总额">
          <span v-html="fmtAmount(endorsedStats.endorsedTotal)" />
        </el-descriptions-item>
      </el-descriptions>

      <!-- 未到期贴现/质押/背书汇总 -->
      <div class="section-title">未到期贴现/质押/背书汇总</div>
      <table class="unexpired-table">
        <thead>
          <tr>
            <th>票据类型</th>
            <th>已贴现未到期</th>
            <th>已质押</th>
            <th>已背书未到期</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in unexpiredSummaryRows" :key="row.category">
            <td class="unexpired-label">{{ row.category }}</td>
            <td class="recon-num" v-html="fmtAmount(row.discountedUnexpired)" />
            <td class="recon-num" v-html="fmtAmount(row.pledged)" />
            <td class="recon-num" v-html="fmtAmount(row.endorsedUnexpired)" />
          </tr>
        </tbody>
      </table>
      <p v-if="!cutoffDate" class="cutoff-hint">请先填写截止日期，以计算未到期贴现/背书金额。</p>

      <!-- 审计说明 -->
      <div class="section-title">三、审计说明</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditNote"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditNote(v || '')"
        />
        <div class="note-actions">
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计说明' : 'AI服务暂不可用'" placement="top">
            <el-button
              size="small"
              :loading="aiLoadingNote"
              :disabled="isReadonly || !aiAvailable"
              @click="generateNoteWithAI"
            >
              🤖 AI
            </el-button>
          </el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-memo-note')">
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 审计结论 -->
      <div class="section-title">四、审计结论</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditConclusion"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditConclusion(v || '')"
        />
        <div class="note-actions">
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计结论' : 'AI服务暂不可用'" placement="top">
            <el-button
              size="small"
              :loading="aiLoadingConclusion"
              :disabled="isReadonly || !aiAvailable"
              @click="generateConclusionWithAI"
            >
              🤖 AI
            </el-button>
          </el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-memo-conclusion')">
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 编制提示 -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
  </div>
</template>

<style scoped>
.d1-tab-memo-reconciliation {
  padding: 12px;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

.audit-objective {
  margin-bottom: 8px;
}

.audit-process {
  font-size: 12px;
  color: #606266;
  margin-bottom: 12px;
  line-height: 1.6;
}

.cutoff-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.cutoff-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.warn-banner {
  margin-bottom: 12px;
}

.overview-panel {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  background: linear-gradient(135deg, #f0f7ff 0%, #eaf4ff 100%);
  border-radius: 12px;
  margin-bottom: 16px;
  border: 1px solid #d9ecff;
}

.overview-info { flex: 1; min-width: 0; }

.overview-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-code {
  font-size: 11px;
  color: #409eff;
  border-color: #b3d8ff;
  background: #fff;
}

.overview-desc {
  margin: 0;
  font-size: 13px;
  color: #606266;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: #909399;
  font-size: 13px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  margin-bottom: 16px;
}

.methodology-collapse {
  margin-bottom: 16px;
  border-radius: 6px;
  border: 1px solid #faecd8;
  border-left: 3px solid #e6a23c;
  background: #fffbf0;
}

.methodology-summary {
  cursor: pointer;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  color: #b88230;
}

.methodology-body {
  padding: 8px 14px 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.method-title { margin: 8px 0 4px; font-size: 13px; }

.method-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 0 4px;
}

.method-title-row .method-title { margin: 0; }

.method-objectives {
  margin: 0 0 8px 1.2em;
  padding: 0;
}

.unexpired-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 8px;
}

.unexpired-table th,
.unexpired-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
}

.unexpired-table th {
  background: #f5f7fa;
  font-weight: 600;
  text-align: center;
}

.unexpired-label {
  font-weight: 600;
  text-align: left !important;
}

.cutoff-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
}

.virtual-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.virtual-hint { margin-bottom: 0; flex: 1; }
.virtual-table { margin-bottom: 8px; }

.memo-table {
  width: 100%;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 18px 0 10px;
}

/* summary 行样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

.summary-label {
  font-weight: 600;
  font-size: 13px;
}

.summary-val {
  font-weight: 600;
}

.auto-calc-val {
  color: #409eff;
  font-weight: 600;
}

.summary-blank {
  min-height: 20px;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 票据号单元格布局（含删除按钮） */
.note-number-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.note-number-cell .el-input {
  flex: 1;
}

.memo-table :deep(.el-table__body td:nth-child(1) .cell) {
  font-size: 13px;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

/* 核对区表格 */
.recon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.recon-table th,
.recon-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  text-align: right;
}

.recon-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.recon-label-col {
  text-align: left !important;
  min-width: 140px;
  font-weight: 600;
}

.recon-num {
  font-variant-numeric: tabular-nums;
}

/* 明细账行浅蓝 */
.ledger-cell {
  background: #ecf5ff;
}

.ledger-warn {
  color: #e6a23c;
  font-weight: 600;
}

/* 差异非零红色 */
.diff-nonzero {
  color: #f56c6c;
  font-weight: 600;
}

.diff-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #e6a23c;
}

.endorsed-stats {
  margin-bottom: 8px;
}

/* 审计说明/结论 */
.note-section {
  margin-bottom: 8px;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

/* 编制提示折叠区 */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
