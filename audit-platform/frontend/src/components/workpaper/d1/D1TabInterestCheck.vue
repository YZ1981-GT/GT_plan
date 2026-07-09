<script setup lang="ts">
/**
 * D1TabInterestCheck.vue — 贴息检查D1-9 HTML渲染
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 11.1
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换头部 + OnlyOffice 健康检查 + GtOnlyOfficeSheet
 * - 工具栏：导出模板/导出数据/导入数据（SHEET_CODE='D1-9'）
 * - 审计目标（只读 el-alert）+ 审计过程（只读描述）
 * - 贴息计算表：13 列 el-table（rows + totalRow 合计行）
 *   由 COLS ColDesc 数组驱动，列类型 text/number/percent/date/select/derived-int/derived-num
 *   - 派生列（贴息天数/应计贴现利息/差异）只读灰底；差异≠0 红色高亮
 *   - 利率列（票面利率/贴现率）小数输入，4 位精度（如 0.05 = 5%）
 *   - 动态行 ✕ 删除按钮 / "添加行"
 *   - 合计行 summary 只读加粗
 * - 差异统计摘要：差异合计/差异笔数/最大单笔差异（喂 AI 结论）
 * - 审计说明 / 审计结论（textarea + 🤖AI + 💬复核）
 * - 编制提示折叠区（<details> 蓝色左边线+浅蓝背景）
 *
 * Requirements: 10.1-10.9, 11.1-11.4, 12.1, 16.1-16.6
 */
import { ref, inject, toRef, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useD1InterestCheck,
  type InterestCheckRow,
} from '../composables/useD1InterestCheck'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
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
  rows,
  totalRow,
  totalDifference,
  differenceCount,
  maxDifference,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  saveAuditNote,
  saveAuditConclusion,
} = useD1InterestCheck({
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

// ─── Column Descriptors (13 列) ──────────────────────────────────────────────

type ColType = 'text' | 'number' | 'percent' | 'date' | 'select' | 'derived-int' | 'derived-num'
interface ColDesc {
  field: keyof InterestCheckRow
  label: string
  width: number
  type: ColType
  options?: string[]
}

const COLS: ColDesc[] = [
  { field: 'noteType', label: '票据类型', width: 140, type: 'select', options: NOTE_TYPE_OPTIONS },
  { field: 'faceValue', label: '票面金额', width: 120, type: 'number' },
  { field: 'faceRate', label: '票面利率(小数,如0.05)', width: 140, type: 'percent' },
  { field: 'issueDate', label: '出票日期', width: 140, type: 'date' },
  { field: 'maturityDate', label: '到期日期', width: 140, type: 'date' },
  { field: 'maturityValue', label: '到期日票据价值', width: 130, type: 'number' },
  { field: 'discountDate', label: '贴现日期', width: 140, type: 'date' },
  { field: 'discountDays', label: '贴息天数', width: 90, type: 'derived-int' },
  { field: 'discountRate', label: '贴现率(小数,如0.05)', width: 140, type: 'percent' },
  { field: 'calculatedInterest', label: '应计贴现利息', width: 120, type: 'derived-num' },
  { field: 'bookedInterest', label: '账面贴现利息', width: 120, type: 'number' },
  { field: 'difference', label: '差异', width: 110, type: 'derived-num' },
  { field: 'remark', label: '备注', width: 160, type: 'text' },
]

// ─── Table Data (rows + totalRow) ─────────────────────────────────────────────

const tableData = computed<InterestCheckRow[]>(() => [...rows.value, totalRow.value])

function getRowClass({ row }: { row: InterestCheckRow }): string {
  return row.rowType === 'summary' ? 'is-summary' : ''
}

// summary 行不可编辑；只读时全不可编辑
function isEditable(row: InterestCheckRow): boolean {
  return !props.isReadonly && row.rowType !== 'summary'
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Change Handlers ───────────────────────────────────────────────────────────

function onNumberChange(rowId: string, field: keyof InterestCheckRow, v: number | undefined) {
  updateCell(rowId, field as string, v ?? 0)
}

function onTextChange(rowId: string, field: keyof InterestCheckRow, v: string) {
  updateCell(rowId, field as string, v || '')
}

// ─── Import/Export ───────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-9')

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// 表格单元格右键 → 发起复核对话（Task 19.1 scaffolding）
function onCellContextMenu(row: InterestCheckRow, _column: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  if (openReviewDialog) openReviewDialog({ sectionId: 'D1-interest-cell', rowId: row.rowId })
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  '贴现利息计算公式：应计贴现利息 = 票面金额（P）× 贴现率（R）× 贴息天数（D）/ 360。其中贴息天数为贴现日至到期日的实际天数（系统按到期日期与贴现日期自动计算），贴现率按银行贴现协议约定的年化利率填写（以小数录入，如 5% 填 0.05）。系统按此公式自动计算"应计贴现利息"并与"账面贴现利息"比较得出差异。',
  '差异追查：差异 = 应计贴现利息 − 账面贴现利息。差异≠0 的行以红色高亮，应逐笔查明原因——可能为贴现率、天数、金额录入错误，或企业账面贴现息计提口径与协议不符、跨期分摊差异等。差异合计、差异笔数、最大单笔差异汇总于"差异统计摘要"，用于评估贴息处理的整体准确性并支持审计结论。',
  '天数计算口径：贴息天数默认按到期日期与贴现日期之间的实际天数计算，分母采用 360 天惯例（与银行贴现业务通行口径一致）。若企业采用 365 天口径或"算头不算尾/算尾不算头"等差异，应在审计说明中记录并评估其影响。',
  '数据来源与核对：贴现金额、贴现率、贴现日期等应与银行贴现协议、贴现凭证、银行回单核对一致；票面金额、票面利率、出票/到期日期应与票据原件或备查簿核对；对差异较大的项目应索取企业计算底稿复核。',
]
</script>

<template>
  <div class="d1-tab-interest-check">
      <div class="tab-header">
        <h4>贴息检查 D1-9</h4>
        <GtReviewTrigger section-id="D1-interest-header" />
      </div>
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        description="检查已贴现应收票据贴息（贴现利息）计算的准确性，验证应计贴现利息与账面贴现利息是否一致，查明差异原因。"
        class="audit-objective"
      />

      <!-- 审计过程 -->
      <div class="audit-process">
        <span class="process-label">审计过程：</span>
        按贴现利息公式 P×R×D/360 逐笔重新计算应计贴现利息，与企业账面贴现利息比较，对差异逐笔追查并汇总评估。
      </div>

      <!-- Toolbar -->
      <div class="table-toolbar">
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
      </div>

      <!-- 贴息计算表 -->
      <div class="section-title">贴息计算表</div>
      <div class="sub-toolbar">
        <el-button size="small" :disabled="isReadonly" @click="addRow()">+ 添加行</el-button>
      </div>
      <el-table
        :data="tableData"
        border
        size="small"
        :row-class-name="getRowClass"
        class="interest-table"
        @cell-contextmenu="onCellContextMenu"
      >
        <el-table-column
          v-for="col in COLS"
          :key="col.field"
          :label="col.label"
          :width="col.width"
          :align="col.type === 'number' || col.type === 'percent' || col.type === 'derived-int' || col.type === 'derived-num' ? 'right' : 'left'"
        >
          <template #default="{ row }: { row: InterestCheckRow }">
            <!-- summary 合计行（只读加粗） -->
            <template v-if="row.rowType === 'summary'">
              <span v-if="col.field === 'noteType'" class="summary-label">{{ row.noteType }}</span>
              <span
                v-else-if="col.field === 'difference'"
                class="summary-val"
                :class="{ 'diff-nonzero': (row.difference as number) !== 0 }"
                v-html="fmtAmount(row.difference as number)"
              />
              <span
                v-else-if="col.type === 'number' || col.type === 'derived-num'"
                class="summary-val"
                v-html="fmtAmount(row[col.field] as number)"
              />
              <span v-else />
            </template>

            <!-- 派生列：贴息天数（只读整数，灰底） -->
            <template v-else-if="col.type === 'derived-int'">
              <span class="derived-cell">{{ row.discountDays }}</span>
            </template>

            <!-- 派生列：应计贴现利息 / 差异（只读金额，灰底；差异≠0 红色高亮） -->
            <template v-else-if="col.type === 'derived-num'">
              <span
                class="derived-cell"
                :class="{ 'diff-nonzero': col.field === 'difference' && (row.difference as number) !== 0 }"
                v-html="fmtAmount(row[col.field] as number)"
              />
            </template>

            <!-- 可编辑单元格 -->
            <template v-else-if="isEditable(row)">
              <el-input-number
                v-if="col.type === 'number'"
                :model-value="row[col.field] as number"
                size="small"
                :controls="false"
                :precision="2"
                @change="(v: number | undefined) => onNumberChange(row.rowId, col.field, v)"
              />
              <el-input-number
                v-else-if="col.type === 'percent'"
                :model-value="row[col.field] as number"
                size="small"
                :controls="false"
                :precision="4"
                :step="0.0001"
                @change="(v: number | undefined) => onNumberChange(row.rowId, col.field, v)"
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
              <!-- 备注列：附带删除按钮 -->
              <div v-else-if="col.field === 'remark'" class="remark-cell">
                <el-input
                  :model-value="row.remark"
                  size="small"
                  @change="(v: string) => onTextChange(row.rowId, 'remark', v)"
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
              <el-input
                v-else
                :model-value="row[col.field] as string"
                size="small"
                @change="(v: string) => onTextChange(row.rowId, col.field, v)"
              />
            </template>

            <!-- 只读 -->
            <template v-else>
              <span
                v-if="col.type === 'number' || col.type === 'percent'"
                v-html="fmtAmount(row[col.field] as number)"
              />
              <span v-else>{{ row[col.field] }}</span>
            </template>
            <GtReviewDot v-if="col.field === 'noteType' && row.rowType !== 'summary'" row-prefix="D1-interest" :row-key="row.rowId" />
          </template>
        </el-table-column>
      </el-table>

      <!-- 差异统计摘要 -->
      <div class="section-title">差异统计摘要</div>
      <el-descriptions :column="3" border size="small" class="diff-summary">
        <el-descriptions-item label="差异合计">
          <span v-html="fmtAmount(totalDifference)" />
        </el-descriptions-item>
        <el-descriptions-item label="差异笔数">
          <span :class="{ 'diff-nonzero': differenceCount > 0 }">{{ differenceCount }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="最大单笔差异">
          <span v-html="fmtAmount(maxDifference)" />
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
          <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-interest-note')">
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
          <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-interest-conclusion')">
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
.d1-tab-interest-check {
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

.audit-process {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.process-label {
  font-weight: 600;
  color: #303133;
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

.interest-table {
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

/* 派生只读列灰底 */
.derived-cell {
  display: inline-block;
  width: 100%;
  padding: 2px 4px;
  background: #f0f2f5;
  border-radius: 2px;
  color: #606266;
}

/* 差异≠0 红色高亮 */
.diff-nonzero {
  color: #f56c6c;
  font-weight: 600;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 备注单元格（含删除按钮） */
.remark-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.remark-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

/* 差异统计摘要 */
.diff-summary {
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
