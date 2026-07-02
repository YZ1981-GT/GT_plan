<script setup lang="ts">
/**
 * D1TabMemoReconciliation.vue — 备查簿核对D1-7 HTML渲染
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 9.1
 *
 * 渲染（HTML 模式）：
 * - 审计目标（只读 el-alert type=info）+ 审计过程说明
 * - 截止日期 el-date-picker（YYYY-MM-DD）
 * - 工具栏：导出模板/导出数据/导入数据（SHEET_CODE='D1-7'）+ 添加银行/商业承兑票据
 * - 31 列宽表 el-table（4 表头分组：基本信息/流转/金额/审定），
 *   票据类型/票据号 fixed=left，动态行可删除，小计/合计 summary 行只读加粗
 * - 核对区（备查簿合计 / 明细账D1-2 / 差异）：差异非零红色，明细账浅蓝取自 D1-2，
 *   crossSheetStatus=error 时占位 '-' + ⚠️
 * - 贴现背书统计区（已贴现总额 / 已背书总额）
 * - 审计说明 / 审计结论（textarea + 🤖AI + 💬复核）
 * - 编制提示折叠区（<details> 蓝色左边线+浅蓝背景）
 * - el-segmented 双模式切换头部
 *
 * Requirements: 4.1-4.8, 5.1-5.6, 6.1-6.5, 12.1, 16.1-16.6
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1MemoReconciliation, type MemoRow } from '../composables/useD1MemoReconciliation'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'
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

// ─── Dual Mode (HTML ↔ OnlyOffice) ──────────────────────────────────────────

const editorMode = ref<'html' | 'oo'>('html')
const ooHealthy = ref(true)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
])

const ooSheetName = computed(() => props.sheetName || '备查簿核对D1-7')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

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
  crossSheetStatus,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  setCutoffDate,
  saveAuditNote,
  saveAuditConclusion,
} = useD1MemoReconciliation({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
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

// ─── Column Descriptors ───────────────────────────────────────────────────────

type ColType = 'text' | 'number' | 'date' | 'select'
interface ColDesc {
  field: keyof MemoRow
  label: string
  width: number
  type: ColType
  options?: string[]
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
  { field: 'endingBalance', label: '年末余额', width: 120, type: 'number' },
  { field: 'unexpiredEndorsedDiscounted', label: '期末未到期背书贴现', width: 160, type: 'number' },
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

const SHEET_CODE = 'D1-7'

async function exportTemplate() {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d1/export-template`, null, {
      params: { sheet: SHEET_CODE },
      responseType: 'blob',
    })
    triggerDownload(res.data, `${SHEET_CODE}_模板.xlsx`)
  } catch { ElMessage.error('导出模板失败') }
}

async function exportData() {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d1/export-data`, null, {
      params: { sheet: SHEET_CODE },
      responseType: 'blob',
    })
    triggerDownload(res.data, `${SHEET_CODE}_数据.xlsx`)
  } catch { ElMessage.error('导出数据失败') }
}

function triggerDownload(data: BlobPart, filename: string) {
  const blob = new Blob([data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function handleImportFile(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d1/import-data`, formData, {
      params: { sheet: SHEET_CODE },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const data = res.data?.data ?? res.data
    ElMessage.success(`成功导入${data.imported_count}行数据`)
    if (data.warning) ElMessage.warning(data.warning)
  } catch (e: any) {
    const errData = e?.response?.data?.data ?? e?.response?.data
    if (e?.response?.status === 400 && errData?.invalid_columns?.length) {
      ElMessage.error(`列名不匹配: ${errData.invalid_columns.join(', ')}`)
    } else {
      ElMessage.error('导入失败')
    }
  }
}

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
  '备查簿应逐笔登记：对每一张银行承兑汇票、商业承兑汇票的收到、背书转让、贴现、到期承兑、退票等全生命周期事项逐笔登记，确保票据流转全过程可追溯。',
  '与明细账（D1-2）核对：备查簿逐笔登记的年初余额、本期收到、本期背书、本期到期、本期贴现、期末余额等汇总数，应与原值明细表 D1-2 相应科目一致；如存在差异应查明原因并在审计说明中记录。',
  '截止日期用于判断票据的期后事项（背书/贴现/到期）是否已终止确认；请填写审计基准日（通常为资产负债表日），据此计算"期末未到期背书贴现"及贴现背书统计。',
  '贴现/背书统计：系统按票据状态自动汇总"已贴现总额"与"已背书总额"，用于评估票据终止确认及应收款项融资/应收票据的列报分类。',
]
</script>

<template>
  <div class="d1-tab-memo-reconciliation">
    <!-- Mode Switcher -->
    <div class="mode-switcher">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <el-tooltip v-if="!ooHealthy" content="OnlyOffice服务不可用" placement="top">
        <span class="oo-disabled-hint">⚠️</span>
      </el-tooltip>
    </div>

    <!-- OnlyOffice mode -->
    <template v-if="editorMode === 'oo'">
      <GtOnlyOfficeSheet :wp-id="wpId" :sheet-name="ooSheetName" :project-id="projectId" />
    </template>

    <!-- HTML mode -->
    <template v-if="editorMode === 'html'">
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        description="通过备查簿逐笔登记应收票据的收到、背书、贴现、到期等全生命周期事项，追踪票据流转过程，并与原值明细表D1-2核对，验证票据业务的完整性与准确性。"
        class="audit-objective"
      />
      <div class="audit-process">
        审计过程：逐笔登记备查簿票据信息 → 与明细账D1-2核对差异 → 统计贴现/背书总额 → 判断终止确认及列报分类。
      </div>

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
        <el-button-group size="small">
          <el-button @click="exportTemplate">导出模板</el-button>
          <el-button @click="exportData">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx"
            :auto-upload="false"
            :on-change="(f: any) => handleImportFile(f.raw)"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
        <el-button-group>
          <el-button size="small" :disabled="isReadonly" @click="addRow('bank')">
            + 添加银行承兑票据
          </el-button>
          <el-button size="small" :disabled="isReadonly" @click="addRow('commercial')">
            + 添加商业承兑票据
          </el-button>
        </el-button-group>
      </div>

      <!-- 31列宽表 -->
      <el-table :data="tableData" border size="small" :row-class-name="getRowClass" class="memo-table" @cell-contextmenu="onCellContextMenu">
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
                <el-input-number
                  v-if="col.type === 'number'"
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
                <el-input-number
                  v-if="col.type === 'number'"
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
                <el-input-number
                  v-if="col.type === 'number'"
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
                <el-input-number
                  v-if="col.type === 'number'"
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
          <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-memo-note')">
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
    </template>
  </div>
</template>

<style scoped>
.d1-tab-memo-reconciliation {
  padding: 12px;
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
}

.summary-val {
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
