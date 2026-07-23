<script setup lang="ts">
/**
 * D1TabEndorsementDetail.vue — 贴现背书明细D1-8 HTML渲染
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 10.1
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换头部 + OnlyOffice 健康检查 + GtOnlyOfficeSheet
 * - 工具栏：导出模板/导出数据/导入数据（SHEET_CODE='D1-8'）
 * - (一)已贴现尚未到期票据检查表：16 列 el-table（discountRows + discountTotal 合计行）
 * - (二)已背书尚未到期票据检查表：16 列 el-table（endorseRows + endorseTotal 合计行）
 *   两表结构一致，由同一 COLS ColDesc 数组 + tableConfigs 驱动渲染
 *   - 会计处理是否正确==='否' 的行红色背景（row-class-name）
 *   - 动态行 ✕ 删除按钮 / "添加行" / "从备查簿导入"（D1-7）
 *   - 合计行 summary 只读加粗
 * - 审计说明 / 审计结论（textarea + 🤖AI + 💬复核）
 * - 编制提示折叠区（<details> 蓝色左边线+浅蓝背景）
 *
 * Requirements: 7.1-7.5, 8.1-8.5, 9.1-9.4, 12.1, 16.1-16.6, 17.1-17.5
 */
import { ref, inject, toRef, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useD1EndorsementDetail,
  type EndorsementRow,
} from '../composables/useD1EndorsementDetail'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import type { MemoRow } from '../composables/useD1MemoReconciliation'
import { pullD5FinancingForD1, buildD1D5Reconcile, type D5FinancingPullResult, type D1D5Reconcile } from '../composables/d1D5FinancingPull'
import { parseNum } from '../composables/useD1FormulaEngine'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useWorkpaperWideTable } from '../composables/useWorkpaperWideTable'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol, virtualSelectCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import http from '@/utils/http'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// 复核对话（Task 19 预留）：仅当 provider 存在时展示 💬 按钮
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  discountRows,
  endorseRows,
  discountTotal,
  endorseTotal,
  auditNote,
  auditConclusion,
  addDiscountRow,
  removeDiscountRow,
  addEndorseRow,
  removeEndorseRow,
  updateCell,
  importFromMemo,
  saveAuditNote,
  saveAuditConclusion,
} = useD1EndorsementDetail({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── Dropdown Options ─────────────────────────────────────────────────────────

const NOTE_TYPE_OPTIONS = ['银行承兑汇票', '商业承兑汇票']
const RATING_OPTIONS = ['AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', '其他']
const YN_OPTIONS = ['是', '否']

// ─── Column Descriptors (16 列，两表共用) ────────────────────────────────────

type ColType = 'text' | 'number' | 'date' | 'select' | 'index'
interface ColDesc {
  field: keyof EndorsementRow
  label: string
  width: number
  type: ColType
  options?: string[]
}

const COLS: ColDesc[] = [
  { field: 'noteType', label: '票据种类', width: 150, type: 'select', options: NOTE_TYPE_OPTIONS },
  { field: 'receivedDate', label: '收到日期', width: 140, type: 'date' },
  { field: 'issuer', label: '出票人', width: 120, type: 'text' },
  { field: 'noteNumber', label: '票据号', width: 140, type: 'text' },
  { field: 'billAmount', label: '汇票金额', width: 120, type: 'number' },
  { field: 'accruedInterest', label: '已计利息', width: 110, type: 'number' },
  { field: 'issueDate', label: '出票日', width: 140, type: 'date' },
  { field: 'maturityDate', label: '到期日', width: 140, type: 'date' },
  { field: 'acceptorBank', label: '承兑银行', width: 120, type: 'text' },
  { field: 'creditRating', label: '信用等级', width: 110, type: 'select', options: RATING_OPTIONS },
  { field: 'discountBank', label: '贴现银行', width: 120, type: 'text' },
  { field: 'discountAmount', label: '贴现金额', width: 120, type: 'number' },
  { field: 'discountInterest', label: '贴现息', width: 110, type: 'number' },
  { field: 'isDerecognized', label: '是否终止确认', width: 120, type: 'select', options: YN_OPTIONS },
  { field: 'isCorrect', label: '会计处理是否正确', width: 140, type: 'select', options: YN_OPTIONS },
  { field: 'indexRef', label: '索引号', width: 160, type: 'index' },
]

const virtualColumns = computed<VirtualColumn[]>(() =>
  COLS.map((col) => {
    const key = String(col.field)
    if (col.type === 'number') return virtualNumCol(key, col.label, col.width, displayPrefs.fmtAmount)
    if (col.type === 'select') return virtualSelectCol(key, col.label, col.width)
    return virtualTextCol(key, col.label, col.width)
  }),
)

const tabBrowseRows = computed(() => {
  const n = Math.max(discountRows.value.length, endorseRows.value.length)
  return Array.from({ length: n }, (_, i) => ({ i }))
})

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: tabBrowseRows,
  virtualColumns,
  tableWidth: 1400,
})

function sectionBrowseRows(data: EndorsementRow[]): EndorsementRow[] {
  return data.filter(r => r.rowType !== 'summary')
}

function sectionBrowseRowCount(data: EndorsementRow[]): number {
  return sectionBrowseRows(data).length
}

// ─── Table Configs (两表由同一数组驱动) ──────────────────────────────────────

type TableKey = 'discount' | 'endorse'

const columnCount = ref(COLS.length)
const discountRowCount = computed(() => discountRows.value.length)
const endorseRowCount = computed(() => endorseRows.value.length)
const discountTableLayout = useWorkpaperWideTable({ rowCount: discountRowCount, columnCount })
const endorseTableLayout = useWorkpaperWideTable({ rowCount: endorseRowCount, columnCount })

function tableLayoutFor(key: TableKey) {
  return key === 'discount' ? discountTableLayout : endorseTableLayout
}

const wpIdRef = toRef(props, 'wpId')
const discountIe = useD1TabImportExport(wpIdRef, 'D1-8')
const endorseIe = useD1TabImportExport(wpIdRef, 'D1-8T')

const tableConfigs = computed(() => [
  {
    key: 'discount' as TableKey,
    title: '（一）已贴现尚未到期票据检查表',
    data: [...discountRows.value, discountTotal.value],
    add: addDiscountRow,
    remove: removeDiscountRow,
    importMemo: () => doImport('discount'),
    ie: discountIe,
  },
  {
    key: 'endorse' as TableKey,
    title: '（二）已背书尚未到期票据检查表',
    data: [...endorseRows.value, endorseTotal.value],
    add: addEndorseRow,
    remove: removeEndorseRow,
    importMemo: () => doImport('endorse'),
    ie: endorseIe,
  },
])

function getRowClass({ row }: { row: EndorsementRow }): string {
  if (row.rowType === 'summary') return 'is-summary'
  if (row.isCorrect === '否') return 'row-error'
  return ''
}

// summary 行不可编辑；只读时全不可编辑
function isEditable(row: EndorsementRow): boolean {
  return !props.isReadonly && row.rowType !== 'summary'
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Change Handlers ───────────────────────────────────────────────────────────

function onNumberChange(table: TableKey, rowId: string, field: keyof EndorsementRow, v: number | undefined) {
  updateCell(table, rowId, field as string, v || 0)
}

function onTextChange(table: TableKey, rowId: string, field: keyof EndorsementRow, v: string) {
  updateCell(table, rowId, field as string, v || '')
}

// ─── 从备查簿 D1-7 导入 ───────────────────────────────────────────────────────

/** 解析 allResponses['D1-memo-rows'] → 合并 bankRows + commercialRows 为 MemoRow[] */
function getMemoRows(): MemoRow[] {
  const raw = props.allResponses.get('D1-memo-rows')?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    const bank = Array.isArray(parsed?.bankRows) ? parsed.bankRows : []
    const commercial = Array.isArray(parsed?.commercialRows) ? parsed.commercialRows : []
    return [...bank, ...commercial] as MemoRow[]
  } catch {
    return []
  }
}

function doImport(table: TableKey) {
  const memoRows = getMemoRows()
  if (!memoRows.length) {
    ElMessage.info('备查簿暂无数据，请先在D1-7中录入')
    return
  }
  importFromMemo(table, memoRows)
  ElMessage.success('已从备查簿D1-7导入')
}

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// 表格单元格右键 → 发起复核对话（Task 19.1 scaffolding）
function onCellContextMenu(row: EndorsementRow, _column: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  if (openReviewDialog) openReviewDialog({ sectionId: 'D1-endorse-cell', rowId: row.rowId })
}

// ─── D5 应收款项融资勾稽 ──────────────────────────────────────────────────────

const d5Loading = ref(false)
const d5Result = ref<D5FinancingPullResult | null>(null)
const d5Reconcile = ref<D1D5Reconcile | null>(null)

/** D1 侧：已贴现未终止确认的汇票金额合计 */
const d1NotDerecognizedTotal = computed(() => {
  return discountRows.value
    .filter(r => r.rowType !== 'summary' && r.isDerecognized !== '是')
    .reduce((s, r) => s + parseNum(r.billAmount), 0)
})

async function handlePullD5() {
  d5Loading.value = true
  try {
    const result = await pullD5FinancingForD1(props.projectId)
    d5Result.value = result
    if (result.status === 'ok') {
      d5Reconcile.value = buildD1D5Reconcile(d1NotDerecognizedTotal.value, result.d5AuditedBalance)
    } else {
      d5Reconcile.value = null
    }
  } catch (e: any) {
    d5Result.value = { status: 'error', message: e?.message || '拉取失败', d5WpId: null, d5AuditedBalance: 0 }
    d5Reconcile.value = null
  } finally {
    d5Loading.value = false
  }
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  '贴现/背书终止确认判断（CAS23《金融资产转移》）：企业将已贴现或已背书转让的应收票据，是否满足金融资产终止确认条件，应根据其与票据所有权相关的风险和报酬转移程度判断——若几乎所有风险和报酬已转移，则终止确认（不再列示于应收票据/应收款项融资）；若仍保留几乎所有风险和报酬（如带追索权贴现商业承兑汇票），则不得终止确认，应作为质押借款处理。',
  '会计处理正确性检查：逐笔核对已贴现/已背书票据的会计处理——终止确认的票据是否已冲减账面、贴现息是否计入财务费用、未终止确认的票据是否同时确认了相应负债（短期借款/其他流动负债）；对"会计处理是否正确"选择"否"的行，系统以红色高亮，应查明原因并在审计说明中记录、必要时提出调整建议。',
  '从备查簿导入：可点击"从备查簿导入"按钮，从备查簿核对表D1-7按票据状态（已贴现/已背书）自动带入相应票据的基本信息、金额、贴现息等；导入后可继续编辑补充"已计利息""会计处理是否正确""索引号"等字段。',
  '信用等级与贴现银行：填写承兑银行信用等级用于评估票据的信用风险，是判断应收款项融资/应收票据列报分类及预期信用损失计量的重要依据；贴现银行、贴现金额、贴现息用于核对贴现业务的完整性与准确性。',
]
</script>

<template>
  <div class="d1-tab-endorsement-detail">
      <div class="tab-header">
        <h4>贴现背书明细 D1-8</h4>
        <GtReviewTrigger section-id="D1-endorsement-header" />
      </div>
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        description="检查已贴现、已背书尚未到期的应收票据，判断其终止确认条件是否满足及相关会计处理是否正确。"
        class="audit-objective"
      />

      <!-- 两张检查表（结构一致，由 tableConfigs 驱动） -->
      <template v-for="cfg in tableConfigs" :key="cfg.key">
        <div class="section-title">{{ cfg.title }}</div>
        <div class="table-toolbar">
          <el-button-group size="small">
            <el-button @click="cfg.ie.onExportTemplate">导出模板</el-button>
            <el-button @click="cfg.ie.onExportData">导出数据</el-button>
            <el-upload
              :show-file-list="false"
              accept=".xlsx"
              :before-upload="cfg.ie.onImportFile"
              style="display:inline-block"
            >
              <el-button size="small">导入数据</el-button>
            </el-upload>
          </el-button-group>
        </div>
        <div class="sub-toolbar">
          <el-button size="small" :disabled="isReadonly" @click="cfg.add()">+ 添加行</el-button>
          <el-button size="small" :disabled="isReadonly" @click="cfg.importMemo()">
            从备查簿导入
          </el-button>
        </div>
        <div v-if="useVirtualScroll" class="virtual-toolbar">
          <el-alert type="info" :closable="false" class="virtual-hint">
            行数较多（{{ sectionBrowseRowCount(cfg.data) }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
          </el-alert>
          <el-button size="small" @click="toggleBrowseMode">
            {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
          </el-button>
        </div>
        <el-table-v2
          v-if="useVirtualScroll && browseMode"
          :columns="virtualColumns"
          :data="sectionBrowseRows(cfg.data)"
          :width="tableWidth"
          :height="tableHeight"
          :row-height="36"
          :header-height="40"
          :row-event-handlers="rowEventHandlers"
          fixed
          class="virtual-table"
        />
        <el-table
          v-if="!useVirtualScroll || !browseMode"
          :data="cfg.data"
          border
          size="small"
          :row-class-name="getRowClass"
          class="endorse-table"
          :max-height="tableLayoutFor(cfg.key).tableMaxHeight"
          @cell-contextmenu="onCellContextMenu"
        >
          <el-table-column
            v-for="col in COLS"
            :key="col.field"
            :label="col.label"
            :width="col.width"
            :align="col.type === 'number' ? 'right' : 'left'"
          >
            <template #default="{ row }: { row: EndorsementRow }">
              <!-- summary 合计行（只读加粗） -->
              <template v-if="row.rowType === 'summary'">
                <span v-if="col.field === 'noteType'" class="summary-label">{{ row.noteType }}</span>
                <span
                  v-else-if="col.type === 'number'"
                  class="summary-val"
                  v-html="fmtAmount(row[col.field] as number)"
                />
                <span v-else />
              </template>

              <!-- 索引号列（GtIndexChip + el-input fallback） -->
              <template v-else-if="col.type === 'index'">
                <div class="index-cell">
                  <el-input
                    :model-value="row.indexRef"
                    placeholder="如 D1-7"
                    size="small"
                    :disabled="!isEditable(row)"
                    @change="(v: string) => onTextChange(cfg.key, row.rowId, 'indexRef', v)"
                  />
                  <GtIndexChip
                    v-if="row.indexRef"
                    :value="row.indexRef"
                    :context-project-id="projectId"
                  />
                  <el-button
                    v-if="row.rowType === 'dynamic' && !isReadonly"
                    type="danger"
                    size="small"
                    text
                    class="delete-btn"
                    @click="cfg.remove(row.rowId)"
                  >
                    ✕
                  </el-button>
                </div>
              </template>

              <!-- 可编辑单元格 -->
              <template v-else-if="isEditable(row)">
                <el-input-number
                  v-if="col.type === 'number'"
                  :model-value="row[col.field] as number"
                  size="small"
                  :controls="false"
                  :precision="2"
                  @change="(v: number) => onNumberChange(cfg.key, row.rowId, col.field, v)"
                />
                <el-date-picker
                  v-else-if="col.type === 'date'"
                  :model-value="row[col.field] as string"
                  type="date"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  size="small"
                  style="width: 100%"
                  @change="(v: string) => onTextChange(cfg.key, row.rowId, col.field, v)"
                />
                <el-select
                  v-else-if="col.type === 'select'"
                  :model-value="row[col.field] as string"
                  size="small"
                  clearable
                  style="width: 100%"
                  @change="(v: string) => onTextChange(cfg.key, row.rowId, col.field, v)"
                >
                  <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                </el-select>
                <el-input
                  v-else
                  :model-value="row[col.field] as string"
                  size="small"
                  @change="(v: string) => onTextChange(cfg.key, row.rowId, col.field, v)"
                />
              </template>

              <!-- 只读 -->
              <template v-else>
                <span v-if="col.type === 'number'" v-html="fmtAmount(row[col.field] as number)" />
                <span v-else>{{ row[col.field] }}</span>
              </template>
              <GtReviewDot v-if="col.field === 'noteType' && row.rowType !== 'summary'" row-prefix="D1-endorsement" :row-key="row.rowId" />
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- 审计说明 -->
      <div class="section-title">审计说明</div>
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
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-endorse-note')">
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 审计结论 -->
      <div class="section-title">审计结论</div>
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
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-endorse-conclusion')">
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- D1-8 ↔ D5 应收款项融资勾稽 -->
      <div class="section-title">D1-8 ↔ D5 应收款项融资勾稽</div>
      <el-card shadow="never" class="reconcile-card">
        <div class="reconcile-toolbar">
          <el-button size="small" type="primary" :loading="d5Loading" @click="handlePullD5">
            勾稽 D5 应收款项融资
          </el-button>
          <span v-if="d5Result && d5Result.status !== 'ok'" class="reconcile-msg warn">{{ d5Result.message }}</span>
        </div>
        <template v-if="d5Reconcile">
          <table class="reconcile-table">
            <thead>
              <tr>
                <th>D1-8 未终止确认合计</th>
                <th>D5-1 审定 FV 合计</th>
                <th>差异</th>
                <th>勾稽结果</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="reconcile-num" v-html="fmtAmount(d5Reconcile.d1NotDerecognizedTotal)" />
                <td class="reconcile-num" v-html="fmtAmount(d5Reconcile.d5AuditedBalance)" />
                <td class="reconcile-num" :class="{ 'diff-warn': !d5Reconcile.matched }" v-html="fmtAmount(d5Reconcile.diff)" />
                <td>
                  <el-tag :type="d5Reconcile.matched ? 'success' : 'warning'" size="small">
                    {{ d5Reconcile.matched ? '勾稽一致' : '存在差异' }}
                  </el-tag>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="!d5Reconcile.matched" class="reconcile-hint">
            差异 {{ d5Reconcile.diff.toLocaleString('zh-CN') }} 元，请核查 D1-8 未终止确认票据与 D5-1 应收款项融资分类是否一致。
          </p>
        </template>
      </el-card>

      <!-- 编制提示 -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
  </div>
</template>

<style scoped>
.d1-tab-endorsement-detail {
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
  margin-bottom: 12px;
}

.table-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 18px 0 10px;
}

.sub-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.virtual-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.virtual-hint { margin-bottom: 0; flex: 1; }
.virtual-table { margin-bottom: 8px; }

.endorse-table {
  width: 100%;
}

/* summary 行样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

.summary-label {
  font-weight: 600;
}

.summary-val {
  font-weight: 600;
}

/* 会计处理不正确行红色高亮 */
:deep(.el-table .row-error td) {
  background-color: #fef0f0 !important;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 索引号单元格（含删除按钮） */
.index-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.index-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
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
  font-size: var(--wp-font-size, 13px);
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

/* D5 勾稽区 */
.reconcile-card {
  margin-bottom: 16px;
}
.reconcile-card :deep(.el-card__body) {
  padding: 12px 16px;
}
.reconcile-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.reconcile-msg.warn {
  font-size: 12px;
  color: #e6a23c;
}
.reconcile-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 8px;
}
.reconcile-table th,
.reconcile-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  text-align: center;
}
.reconcile-table th {
  background: #f5f7fa;
  font-weight: 600;
}
.reconcile-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.diff-warn {
  color: #e6a23c !important;
  font-weight: 600;
}
.reconcile-hint {
  font-size: 12px;
  color: #e6a23c;
  margin: 4px 0 0;
}
</style>
