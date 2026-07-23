<script setup lang="ts">
/**
 * F3TabDetail — F3-2 期末应付票据明细表（源表宽表 + 分段 + 列设置）
 * Spec: .kiro/specs/f3-notes-payable/ Task 6.2
 * 比照 D4TabRevenueDetail（精美组件 gold-standard）
 */
import { ref, computed, watch, toRef, inject, type Ref } from 'vue'
import { useF3Detail, type F3NoteDetailRow, type F3DetailColumn } from '../composables/useF3Detail'
import { useF3AiGenerate, type F3AiSection } from '../composables/useF3AiGenerate'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import F3SheetAttachments from './F3SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
function onImported() { reloadWorkpaperData?.() }

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  activeSegment,
  filteredRows,
  subtotalRow,
  filledCount,
  abnormalCount,
  searchQuery,
  addRow,
  removeRow,
  updateCell,
  rowClassName,
  basicColumns,
  infoColumns,
  auditColumns,
  allColumns,
} = useF3Detail({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const viewMode = ref<'wide' | 'segment'>('wide')
const columnDialogVisible = ref(false)
const COLUMN_PREF_KEY = 'gt:f3-2:visible-columns'
function loadVisibleColumns(): string[] {
  const defaults = allColumns.map((col) => String(col.prop))
  try {
    const parsed = JSON.parse(localStorage.getItem(COLUMN_PREF_KEY) || '[]')
    if (!Array.isArray(parsed) || parsed.length === 0) return defaults
    const valid = new Set(defaults)
    const selected = parsed.filter((prop: unknown) => typeof prop === 'string' && valid.has(prop))
    for (const required of ['seq', 'ticketNo', 'noteType']) {
      if (!selected.includes(required)) selected.push(required)
    }
    return selected.length ? selected : defaults
  } catch {
    return defaults
  }
}
const visibleColumnProps = ref<string[]>(loadVisibleColumns())
watch(visibleColumnProps, (value) => {
  try { localStorage.setItem(COLUMN_PREF_KEY, JSON.stringify(value)) } catch { /* ignore */ }
}, { deep: true })

const activeColumns = computed<F3DetailColumn[]>(() => {
  const source = viewMode.value === 'wide'
    ? allColumns
    : activeSegment.value === 'basic'
      ? basicColumns
      : activeSegment.value === 'detail'
        ? infoColumns
        : auditColumns
  return source.filter((col) => visibleColumnProps.value.includes(String(col.prop)))
})

const DETAIL_SCROLL_THRESHOLD = 50
const useDetailScroll = computed(() => filteredRows.value.length > DETAIL_SCROLL_THRESHOLD)

function isFormulaCol(col: F3DetailColumn): boolean {
  return !!col.formula || [
    'termDays', 'maturityBucket', 'overdueDays', 'closingUnadjusted', 'closingAdjusted', 'isOverdue',
  ].includes(col.prop as string)
}

function displayValue(row: F3NoteDetailRow, prop: string): string {
  const v = (row as any)[prop]
  if (prop === 'seq') return String(v ?? '')
  if (typeof v === 'number') return fmtAmount(v)
  return v ?? ''
}

// ─── 审计说明 / 审计结论（F3 约定：写入 allResponses + f3:save-items 事件持久化） ───
const NOTE_KEY = 'F3-2-note'
const CONCLUSION_KEY = 'F3-2-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const { aiAvailable, loading: aiLoading, generateAndConfirm } =
  useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

function persistAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void { if (props.isReadonly) return; auditNote.value = val; persistAudit(NOTE_KEY, val) }
function saveAuditConclusion(val: string): void { if (props.isReadonly) return; auditConclusion.value = val; persistAudit(CONCLUSION_KEY, val) }

watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => { if (typeof v === 'string') auditNote.value = v }, { immediate: true })
watch(() => props.allResponses.get(CONCLUSION_KEY)?.remark, (v) => { if (typeof v === 'string') auditConclusion.value = v }, { immediate: true })

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F3-2',
    accountCode: '2201',
    rowCount: filledCount.value,
    abnormalCount: abnormalCount.value,
    totals: {
      openingBalance: subtotalRow.value.openingBalance,
      currentIssued: subtotalRow.value.currentIssued,
      currentAccepted: subtotalRow.value.currentAccepted,
      closingUnadjusted: subtotalRow.value.closingUnadjusted,
      aje: subtotalRow.value.aje,
      rje: subtotalRow.value.rje,
      closingAdjusted: subtotalRow.value.closingAdjusted,
      accruedInterest: subtotalRow.value.accruedInterest,
      depositAmount: subtotalRow.value.depositAmount,
    },
    exceptions: filteredRows.value
      .filter((row) => row.overdueDays > 0 || Math.abs(row.aje) > 0.005 || Math.abs(row.rje) > 0.005)
      .slice(0, 20)
      .map((row) => ({
        ticketNo: row.ticketNo,
        noteType: row.noteType,
        drawer: row.drawer,
        acceptor: row.acceptor,
        maturityBucket: row.maturityBucket,
        closingAdjusted: row.closingAdjusted,
        aje: row.aje,
        rje: row.rje,
        isConfirmed: row.isConfirmed,
      })),
  }
}

async function runAi(section: F3AiSection): Promise<void> {
  if (props.isReadonly) return
  const isNote = section === 'detail-note'
  const text = await generateAndConfirm(
    section,
    isNote ? auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 应付票据明细审计说明' : 'AI 生成 · 应付票据明细审计结论',
  )
  if (!text) return
  if (isNote) saveAuditNote(text)
  else saveAuditConclusion(text)
}

function resetColumns(): void {
  visibleColumnProps.value = allColumns.map((col) => String(col.prop))
}

// P1-6 保证金联动 / P1-7 函证提示
const depositTotal = computed(() => subtotalRow.value.depositAmount)
const confirmSummary = computed(() => {
  const filled = filteredRows.value.filter((r) => r.ticketNo || r.faceValue)
  const confirmed = filled.filter((r) => r.isConfirmed === '是').length
  const bankUnconfirmed = filled.filter(
    (r) => (r.noteType || '').includes('银行') && r.isConfirmed !== '是',
  ).length
  return { total: filled.length, confirmed, bankUnconfirmed }
})
</script>

<template>
  <div class="f3-tab-detail">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按票据逐张登记：票据号、类别、关联方类型、出票人/承兑人/收款人、出票及到期日、利率、承兑与函证情况。</p>
        <p>2. 余额逻辑：期末未审数＝期初余额＋本期开票－本期承兑；期末审定数＝期末未审数＋账项调整＋重分类调整。</p>
        <p>3. 到期账龄由系统按到期日自动枚举为未到期、逾期1-30天、31-90天、91-180天、181天以上；逾期行自动高亮并纳入 AI 异常分析。</p>
        <p>4. 票据类别、关联方类型、是否承兑、是否函证均使用枚举录入；保证金应与其他货币资金勾稽，异常票据应结合征信、合同与实物流转核查。</p>
        <p>5. 支持全字段宽表、三区段编辑和列设置；导入导出模板与本表字段一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：应付票据明细真实存在、记录完整，票据种类与到期状态分类准确，为审定表与逾期检查提供明细支撑。"
      class="objective-alert"
    />

    <!-- P1-6 保证金受限联动提示 -->
    <el-alert v-if="depositTotal > 0" type="warning" :closable="false" class="link-alert">
      票据保证金合计 {{ fmtAmount(depositTotal) }} 元属受限货币资金，应重分类至"其他货币资金"，并在货币资金(E1)受限资产及附注中披露。
    </el-alert>
    <!-- P1-7 银行承兑函证提示 -->
    <el-alert v-if="confirmSummary.bankUnconfirmed > 0" type="info" :closable="false" class="link-alert">
      {{ confirmSummary.bankUnconfirmed }} 张银行承兑汇票尚未函证，建议纳入银行询证函(E 货币资金/银行函证)核对承兑额度与保证金。（已函证 {{ confirmSummary.confirmed }}/{{ confirmSummary.total }}）
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-input v-model="searchQuery" placeholder="搜索票据号/关系人/类别..." size="small" clearable style="width:220px" />
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="wide">全字段宽表</el-radio-button>
          <el-radio-button value="segment">分段编辑</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="columnDialogVisible = true">⚙ 列设置</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar
          :wp-id="wpId"
          :project-id="projectId"
          sheet="F3-2"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F3-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">已填 {{ filledCount }} 笔</el-tag>
        <el-tag v-if="abnormalCount" size="small" type="danger">异常 {{ abnormalCount }} 笔</el-tag>
      </div>
    </div>

    <F3SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F3-2" label="明细表附件" />

    <el-tabs v-if="viewMode === 'segment'" v-model="activeSegment" type="border-card" class="segment-tabs">
      <el-tab-pane name="basic" label="票据身份(7列)" />
      <el-tab-pane name="detail" label="条款与到期账龄(8列)" />
      <el-tab-pane name="audit" label="余额与核对(12列)" />
    </el-tabs>

    <div v-if="useDetailScroll" class="scroll-hint">共 {{ filteredRows.length }} 行 · 固定表头滚动</div>

    <el-table
      :data="filteredRows"
      border
      size="small"
      :row-class-name="rowClassName"
      :max-height="useDetailScroll ? 480 : undefined"
      class="detail-wide-table"
      style="width: 100%; margin-top: 8px"
    >
      <el-table-column
        v-for="col in activeColumns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth || 100"
        :fixed="viewMode === 'wide' && col.sticky ? 'left' : undefined"
        :class-name="isFormulaCol(col) ? 'auto-calc-col' : ''"
      >
        <template #header>
          <el-tooltip v-if="col.formula" :content="col.formula" placement="top">
            <span class="formula-header">{{ col.label }}</span>
          </el-tooltip>
          <span v-else>{{ col.label }}</span>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="col.editable && !isReadonly && col.inputType === 'select'"
            :model-value="(row as any)[col.prop]"
            size="small"
            @update:model-value="(v: any) => updateCell(row.rowId, col.prop as string, v)"
          >
            <el-option v-for="option in col.options" :key="option" :label="option" :value="option" />
          </el-select>
          <el-date-picker
            v-else-if="col.editable && !isReadonly && col.inputType === 'date'"
            :model-value="(row as any)[col.prop]"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            @update:model-value="(v: string | null) => updateCell(row.rowId, col.prop as string, v || '')"
          />
          <el-input-number
            v-else-if="col.editable && !isReadonly && col.inputType === 'number'"
            :model-value="(row as any)[col.prop]"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number | undefined) => updateCell(row.rowId, col.prop as string, v ?? 0)"
          />
          <el-input
            v-else-if="col.editable && !isReadonly && col.prop !== 'seq'"
            :model-value="(row as any)[col.prop]"
            size="small"
            @change="(v: any) => updateCell(row.rowId, col.prop as string, v)"
          />
          <el-tag
            v-else-if="col.prop === 'maturityBucket'"
            size="small"
            :type="row.overdueDays > 90 ? 'danger' : row.overdueDays > 0 ? 'warning' : 'success'"
          >{{ row.maturityBucket }}</el-tag>
          <span v-else :class="{ 'formula-cell': isFormulaCol(col) }">{{ displayValue(row, col.prop as string) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="subtotal-bar">
      合计 — 期初: {{ fmtAmount(subtotalRow.openingBalance) }} |
      本期开票: {{ fmtAmount(subtotalRow.currentIssued) }} |
      本期承兑: {{ fmtAmount(subtotalRow.currentAccepted) }} |
      期末未审: {{ fmtAmount(subtotalRow.closingUnadjusted) }} |
      期末审定: {{ fmtAmount(subtotalRow.closingAdjusted) }} |
      保证金: {{ fmtAmount(subtotalRow.depositAmount) }}
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('detail-note')">🤖 AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：明细核对情况、票据种类与到期状态分类、逾期票据处理及与审定表/试算表的核对结果。"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('detail-conclusion')">🤖 AI 生成审计结论</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：明细表是否真实完整、期末余额合计与审定表/试算表核对是否一致。"
        @change="(v: string) => saveAuditConclusion(v)"
      />
    </el-card>

    <el-dialog v-model="columnDialogVisible" title="F3-2 列设置" width="720px">
      <el-checkbox-group v-model="visibleColumnProps" class="column-setting-grid">
        <el-checkbox
          v-for="col in allColumns"
          :key="String(col.prop)"
          :value="String(col.prop)"
          :disabled="col.prop === 'seq' || col.prop === 'ticketNo' || col.prop === 'noteType'"
        >{{ col.label }}</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="resetColumns">恢复全部列</el-button>
        <el-button type="primary" @click="columnDialogVisible = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.f3-tab-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-detail :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
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
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.link-alert {
  margin-bottom: 8px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
.formula-cell {
  background: #f5f7fa;
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
}
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
:deep(.overdue-row td) {
  background: #fdf6ec !important;
}
.subtotal-bar {
  margin-top: 8px;
  font-weight: 600;
  text-align: right;
}
.scroll-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
  text-align: right;
}
.segment-tabs :deep(.el-tabs__content) {
  display: none;
}
.detail-wide-table :deep(.el-table__body-wrapper),
.detail-wide-table :deep(.el-scrollbar__wrap) {
  overflow-x: auto;
}
.column-setting-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 12px;
  max-height: 52vh;
  overflow-y: auto;
}
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
