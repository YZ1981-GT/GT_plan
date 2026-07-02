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
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useD1EndorsementDetail,
  type EndorsementRow,
} from '../composables/useD1EndorsementDetail'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import type { MemoRow } from '../composables/useD1MemoReconciliation'
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../GtIndexChip.vue'
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

const ooSheetName = computed(() => props.sheetName || '贴现背书明细D1-8')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

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
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
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

// ─── Table Configs (两表由同一数组驱动) ──────────────────────────────────────

type TableKey = 'discount' | 'endorse'

const tableConfigs = computed(() => [
  {
    key: 'discount' as TableKey,
    title: '（一）已贴现尚未到期票据检查表',
    data: [...discountRows.value, discountTotal.value],
    add: addDiscountRow,
    remove: removeDiscountRow,
    importMemo: () => doImport('discount'),
  },
  {
    key: 'endorse' as TableKey,
    title: '（二）已背书尚未到期票据检查表',
    data: [...endorseRows.value, endorseTotal.value],
    add: addEndorseRow,
    remove: removeEndorseRow,
    importMemo: () => doImport('endorse'),
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

// ─── Import/Export ───────────────────────────────────────────────────────────

const SHEET_CODE = 'D1-8'

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
function onCellContextMenu(row: EndorsementRow, _column: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  if (openReviewDialog) openReviewDialog({ sectionId: 'D1-endorse-cell', rowId: row.rowId })
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
        description="检查已贴现、已背书尚未到期的应收票据，判断其终止确认条件是否满足及相关会计处理是否正确。"
        class="audit-objective"
      />

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
      </div>

      <!-- 两张检查表（结构一致，由 tableConfigs 驱动） -->
      <template v-for="cfg in tableConfigs" :key="cfg.key">
        <div class="section-title">{{ cfg.title }}</div>
        <div class="sub-toolbar">
          <el-button size="small" :disabled="isReadonly" @click="cfg.add()">+ 添加行</el-button>
          <el-button size="small" :disabled="isReadonly" @click="cfg.importMemo()">
            从备查簿导入
          </el-button>
        </div>
        <el-table
          :data="cfg.data"
          border
          size="small"
          :row-class-name="getRowClass"
          class="endorse-table"
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

      <!-- 编制提示 -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
    </template>
  </div>
</template>

<style scoped>
.d1-tab-endorsement-detail {
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
