<script setup lang="ts">
/**
 * F4TabDetail — F4-2 应付账款明细表
 * 严格对齐源表A:AA 27列，支持宽表/分段编辑、列设置、账龄枚举快捷分配、
 * 双账龄勾稽、F4-1联动、AI审计说明/结论及导入导出。
 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import {
  useF4Detail,
  type APDetailRow,
  type F4DetailColumn,
} from '../composables/useF4Detail'
import { overOneYearKeys } from '../composables/f4AgingModel'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import F4ImportExportToolbar from './F4ImportExportToolbar.vue'
import F4SheetAttachments from './F4SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)

const {
  activeSegment,
  rows,
  filteredRows,
  subtotalRow,
  filledCount,
  abnormalCount,
  searchQuery,
  loadRows,
  addRow,
  removeRow,
  updateCell,
  allocateAging,
  rowClassName,
  segments,
  segKeys,
  agingPreset,
  basicColumns,
  agingColumns,
  auditColumns,
  allColumns,
} = useF4Detail({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

async function onImported(): Promise<void> {
  if (reloadWorkpaperData) await reloadWorkpaperData()
  loadRows()
}

function fmtAmount(value: number): string {
  if (Math.abs(value) < 0.005) return '-'
  const text = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${text})` : text
}

// ─── 宽表 / 分段 / 列设置 ────────────────────────────────────────────────────
const viewMode = ref<'wide' | 'segment'>('wide')
const columnDialogVisible = ref(false)
const COLUMN_PREF_KEY = 'gt:f4-2:visible-columns'

function defaultVisibleColumns(): string[] {
  return allColumns.value.map((column) => String(column.prop))
}

function loadVisibleColumns(): string[] {
  const defaults = defaultVisibleColumns()
  try {
    const parsed = JSON.parse(localStorage.getItem(COLUMN_PREF_KEY) || '[]')
    if (!Array.isArray(parsed) || parsed.length === 0) return defaults
    const valid = new Set(defaults)
    const selected = parsed.filter((item: unknown) =>
      typeof item === 'string' && valid.has(item),
    )
    for (const required of ['creditor', 'closingUnadjusted', 'closingAdjusted']) {
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

// 账龄段变化会引入新的账龄列（prop 形如 agingCurrent.y3to4）：默认显示，避免被旧偏好隐藏
watch(allColumns, (columns) => {
  const known = new Set(visibleColumnProps.value)
  const appended = columns
    .map((column) => String(column.prop))
    .filter((prop) => !known.has(prop) && prop.startsWith('aging'))
  if (appended.length) visibleColumnProps.value = [...visibleColumnProps.value, ...appended]
}, { immediate: true })

const activeColumns = computed<F4DetailColumn[]>(() => {
  const source = viewMode.value === 'wide'
    ? allColumns.value
    : activeSegment.value === 'basic'
      ? basicColumns
      : activeSegment.value === 'aging'
        ? [
          ...basicColumns.slice(0, 4),
          basicColumns[basicColumns.length - 1],
          ...agingColumns.value,
        ]
        : [
          ...basicColumns.slice(0, 4),
          basicColumns[basicColumns.length - 1],
          ...auditColumns.value,
        ]
  return source.filter((column) => visibleColumnProps.value.includes(String(column.prop)))
})

function resetColumns(): void {
  visibleColumnProps.value = defaultVisibleColumns()
}

function isFormulaColumn(column: F4DetailColumn): boolean {
  return !!column.formula
}

/** 支持 nested 账龄 prop（`agingCurrent.within1`）的取值 */
function cellValue(row: APDetailRow, prop: string): any {
  if (prop.includes('.')) {
    const [group, key] = prop.split('.')
    return (row as any)[group]?.[key] ?? 0
  }
  return (row as any)[prop]
}

function displayValue(row: APDetailRow, prop: string): string {
  const value = cellValue(row, prop)
  if (typeof value === 'number') return fmtAmount(value)
  return String(value ?? '')
}

const useFixedHeight = computed(() => filteredRows.value.length > 35)

// 「1 年以上」段由 dayFrom>=366 派生（禁硬编码档位）
const overOneYearSegKeys = computed(() => overOneYearKeys(segments.value))
function overOneYearAudited(row: APDetailRow): number {
  return overOneYearSegKeys.value.reduce((sum, key) => sum + (row.agingAudited?.[key] ?? 0), 0)
}

// ─── 账龄枚举快捷分配 ────────────────────────────────────────────────────────
function handleAgingCommand(rowId: string, command: string): void {
  const [stage, segKey] = command.split(':') as ['unadjusted' | 'audited', string]
  allocateAging(rowId, stage, segKey)
}

// ─── 审计说明 / 结论及AI ─────────────────────────────────────────────────────
const NOTE_KEY = 'F4-2-audit-note'
const CONCLUSION_KEY = 'F4-2-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

watch(
  () => props.allResponses.get(NOTE_KEY)?.remark,
  (value) => { if (typeof value === 'string') auditNote.value = value },
  { immediate: true },
)
watch(
  () => props.allResponses.get(CONCLUSION_KEY)?.remark,
  (value) => { if (typeof value === 'string') auditConclusion.value = value },
  { immediate: true },
)

function persistText(key: string, value: string): void {
  if (props.isReadonly) return
  const item = { item_id: key, conclusion: null, remark: value }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
}

function saveAuditNote(value: string): void {
  auditNote.value = value
  persistText(NOTE_KEY, value)
}

function saveAuditConclusion(value: string): void {
  auditConclusion.value = value
  persistText(CONCLUSION_KEY, value)
}

function aiContext(): Record<string, unknown> {
  const meaningfulRows = rows.value.filter((row) =>
    row.creditor || Math.abs(row.closingUnadjusted) >= 0.01,
  )
  return {
    sheet: 'F4-2',
    accountCode: '2202',
    rowCount: meaningfulRows.length,
    abnormalCount: abnormalCount.value,
    totals: {
      openingUnadjusted: subtotalRow.value.openingUnadjusted,
      openingAje: subtotalRow.value.openingAje,
      openingRje: subtotalRow.value.openingRje,
      openingAdjusted: subtotalRow.value.openingAdjusted,
      currentDebit: subtotalRow.value.currentDebit,
      currentCredit: subtotalRow.value.currentCredit,
      entityReclassification: subtotalRow.value.entityReclassification,
      closingUnadjusted: subtotalRow.value.closingUnadjusted,
      closingAje: subtotalRow.value.closingAje,
      closingRje: subtotalRow.value.closingRje,
      closingAdjusted: subtotalRow.value.closingAdjusted,
      subsequentPayment: subtotalRow.value.subsequentPayment,
    },
    aging: {
      preset: agingPreset.value,
      segments: segments.value.map((seg) => seg.label),
      unadjusted: segKeys.value.map((key) => subtotalRow.value.agingCurrent?.[key] ?? 0),
      audited: segKeys.value.map((key) => subtotalRow.value.agingAudited?.[key] ?? 0),
      unadjustedMatches: !subtotalRow.value.unadjustedAgingMismatch,
      auditedMatches: !subtotalRow.value.auditedAgingMismatch,
    },
    exceptions: meaningfulRows
      .filter((row) =>
        row.unadjustedAgingMismatch
        || row.auditedAgingMismatch
        || row.subsequentPaymentExceedsBalance
        || Math.abs(row.closingAje) >= 0.01
        || Math.abs(row.closingRje) >= 0.01
        || Math.abs(overOneYearAudited(row)) >= 0.01,
      )
      .slice(0, 30)
      .map((row) => ({
        creditor: row.creditor,
        relatedPartyType: row.relatedPartyType,
        paymentNature: row.paymentNature,
        closingUnadjusted: row.closingUnadjusted,
        closingAdjusted: row.closingAdjusted,
        closingAje: row.closingAje,
        closingRje: row.closingRje,
        overOneYearAudited: overOneYearAudited(row),
        subsequentPayment: row.subsequentPayment,
        remark: row.remark,
      })),
  }
}

async function runAi(section: 'detail-note' | 'detail-conclusion'): Promise<void> {
  if (props.isReadonly) return
  const isNote = section === 'detail-note'
  const generated = await generateAndConfirm(
    section,
    isNote ? auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · F4-2审计说明' : 'AI 生成 · F4-2审计结论',
  )
  if (!generated) return
  if (isNote) saveAuditNote(generated)
  else saveAuditConclusion(generated)
}
</script>

<template>
  <div class="f4-tab-detail">
    <details class="guidance-details">
      <summary>📋 编制思路、公式与风险提示</summary>
      <div class="guidance-content">
        <p>1. 按债权人逐户登记，身份字段采用源表枚举：关联方类型为“合并范围内关联方/合并范围外关联方/非关联方”，款项性质为“货款/工程款/设备款/服务费/其他”。</p>
        <p>2. 期初审定余额＝期初未审余额＋期初账项调整＋期初重分类调整；期末余额＝期初未审余额＋贷方发生－借方发生。</p>
        <p>3. 期末未审余额＝期末余额＋被审计单位重分类调整；审定数＝期末未审余额＋账项调整＋重分类调整。</p>
        <p>4. 账龄档位取自<strong>项目账龄配置</strong>（3年段／5年段／自定义，当前生效：{{ segments.map(s => s.label).join(' / ') }}）；未审账龄各段合计必须等于期末未审余额，审定账龄各段合计必须等于审定数；可使用每行“账龄分配”按段将余额快捷填入。</p>
        <p>5. 账龄超过1年的大额款项应说明未偿还/未结转原因及期后偿还情况；3年以上款项、关联方款项、重大调整和期后付款超过期末余额的项目应重点关注。</p>
        <p>6. 支持全字段宽表、分段编辑、个性化列设置及与源表27列一致的导入导出；本表自动汇总联动F4-1审定表。</p>
      </div>
    </details>

    <el-alert
      class="objective-alert"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：验证应付账款逐户余额真实、完整、计价与分类准确；期初、发生额、期末未审、调整、审定及双层账龄形成可追溯审计链，并为F4-1、长期挂账及关联方检查提供明细基础。"
    />

    <el-alert
      v-if="subtotalRow.unadjustedAgingMismatch || subtotalRow.auditedAgingMismatch"
      type="error"
      :closable="false"
      class="risk-alert"
    >
      <span v-if="subtotalRow.unadjustedAgingMismatch">
        未审账龄合计 {{ fmtAmount(subtotalRow.unadjustedAgingTotal) }} ≠ 期末未审余额 {{ fmtAmount(subtotalRow.closingUnadjusted) }}；
      </span>
      <span v-if="subtotalRow.auditedAgingMismatch">
        审定账龄合计 {{ fmtAmount(subtotalRow.auditedAgingTotal) }} ≠ 审定数 {{ fmtAmount(subtotalRow.closingAdjusted) }}。
      </span>
      请检查红色行的账龄分配。
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchQuery"
          placeholder="搜索债权人/公司代码/关联方/款项性质"
          clearable
          size="small"
          style="width: 270px"
        />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="wide">全字段宽表</el-radio-button>
          <el-radio-button value="segment">分段编辑</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="columnDialogVisible = true">⚙ 列设置</el-button>
      </div>
      <div class="toolbar-right">
        <F4ImportExportToolbar
          :wp-id="wpId"
          :project-id="projectId"
          sheet="F4-2"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <GtIndexChip value="wp:F4-1" :context-project-id="projectId" />
        <el-tag size="small" type="warning">账龄 {{ segments.length }} 段</el-tag>
        <el-tag size="small" type="info">已填 {{ filledCount }} 笔</el-tag>
        <el-tag v-if="abnormalCount" size="small" type="danger">异常 {{ abnormalCount }} 笔</el-tag>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-2-detail')">复核</el-button>
      </div>
    </div>

    <F4SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F4-2" label="明细表附件" />

    <el-tabs
      v-if="viewMode === 'segment'"
      v-model="activeSegment"
      type="border-card"
      class="segment-tabs"
    >
      <el-tab-pane name="basic" label="身份·期初·本期变动（A:M）" />
      <el-tab-pane name="aging" label="未审账龄·函证·期后（N:Q/Y:AA）" />
      <el-tab-pane name="audit" label="调整·审定账龄（R:X）" />
    </el-tabs>

    <el-alert
      v-if="viewMode === 'segment' && activeSegment === 'aging'"
      type="warning"
      :closable="false"
      class="inline-tip"
      title="账龄提示：超过1年的大额应付账款需说明未偿还或未结转原因；超过3年以上的款项必须说明原因，并核查期后是否偿还。"
    />

    <el-table
      :data="filteredRows"
      border
      size="small"
      :row-class-name="rowClassName"
      :max-height="useFixedHeight ? 520 : undefined"
      class="detail-wide-table"
    >
      <el-table-column type="index" label="序号" width="58" fixed="left" />
      <el-table-column
        v-for="column in activeColumns"
        :key="String(column.prop)"
        :prop="String(column.prop)"
        :label="column.label"
        :width="column.width"
        :min-width="column.minWidth || 100"
        :fixed="column.prop === 'creditor' ? 'left' : undefined"
        :class-name="isFormulaColumn(column) ? 'auto-calc-col' : ''"
        :align="column.inputType === 'number' || column.formula ? 'right' : 'left'"
      >
        <template #header>
          <el-tooltip v-if="column.formula" :content="column.formula" placement="top">
            <span class="formula-header">{{ column.label }}</span>
          </el-tooltip>
          <span v-else>{{ column.label }}</span>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="column.editable && !isReadonly && column.inputType === 'select'"
            :model-value="cellValue(row, String(column.prop))"
            size="small"
            clearable
            filterable
            @update:model-value="(value: any) => updateCell(row.rowId, String(column.prop), value)"
          >
            <el-option
              v-for="option in column.options"
              :key="option"
              :label="option"
              :value="option"
            />
          </el-select>
          <el-input-number
            v-else-if="column.editable && !isReadonly && column.inputType === 'number'"
            :model-value="cellValue(row, String(column.prop))"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(value: number | undefined) => updateCell(row.rowId, String(column.prop), value ?? 0)"
          />
          <el-input
            v-else-if="column.editable && !isReadonly"
            :model-value="cellValue(row, String(column.prop))"
            size="small"
            :type="column.prop === 'remark' ? 'textarea' : 'text'"
            :autosize="column.prop === 'remark' ? { minRows: 1, maxRows: 3 } : undefined"
            @change="(value: string) => updateCell(row.rowId, String(column.prop), value)"
          />
          <span
            v-else
            :class="{
              'formula-cell': isFormulaColumn(column),
              'mismatch-cell':
                (column.prop === 'closingUnadjusted' && row.unadjustedAgingMismatch)
                || (column.prop === 'closingAdjusted' && row.auditedAgingMismatch),
            }"
          >{{ displayValue(row, String(column.prop)) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="150" fixed="right" align="center">
        <template #default="{ row }">
          <el-dropdown
            size="small"
            trigger="click"
            :disabled="isReadonly"
            @command="(command: string) => handleAgingCommand(row.rowId, command)"
          >
            <el-button link type="primary" size="small">账龄分配⌄</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>按期末未审余额分配</el-dropdown-item>
                <el-dropdown-item
                  v-for="seg in segments"
                  :key="`u-${seg.key}`"
                  :command="`unadjusted:${seg.key}`"
                >{{ seg.label }}</el-dropdown-item>
                <el-dropdown-item divided disabled>按审定数分配</el-dropdown-item>
                <el-dropdown-item
                  v-for="seg in segments"
                  :key="`a-${seg.key}`"
                  :command="`audited:${seg.key}`"
                >{{ seg.label }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button
            link
            type="danger"
            size="small"
            :disabled="isReadonly"
            @click="removeRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="subtotal-bar">
      <span>合计</span>
      <span>期初未审 {{ fmtAmount(subtotalRow.openingUnadjusted) }}</span>
      <span>期初审定 {{ fmtAmount(subtotalRow.openingAdjusted) }}</span>
      <span>借方 {{ fmtAmount(subtotalRow.currentDebit) }}</span>
      <span>贷方 {{ fmtAmount(subtotalRow.currentCredit) }}</span>
      <span>期末未审 {{ fmtAmount(subtotalRow.closingUnadjusted) }}</span>
      <span>审定 {{ fmtAmount(subtotalRow.closingAdjusted) }}</span>
      <span>期后付款 {{ fmtAmount(subtotalRow.subsequentPayment) }}</span>
    </div>

    <el-card shadow="never" class="audit-text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">三、审计说明</div>
            <div class="card-hint">应覆盖：期初及总分账核对、重大余额变动、重大本期发生、1年以上大额挂账、期后付款超过期末余额的原因。</div>
          </div>
          <div class="card-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="runAi('detail-note')"
            >🤖 AI填写说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-2-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 6, maxRows: 16 }"
        :disabled="isReadonly"
        placeholder="1. 期初数与上期审定数、期末总账/明细账/报表核对情况；&#10;2. 期末余额重大变动原因；&#10;3. 大额发生额原因；&#10;4. 超过1年大额应付账款的性质及发生原因；&#10;5. 期后付款超过资产负债表日余额的原因。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">四、审计结论</div>
            <div class="card-hint">根据明细完整性、双层账龄勾稽、调整事项和审计证据选择A/B/C口径。</div>
          </div>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('detail-conclusion')"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述重大不符事项作为调整事项外，其余未见异常。C、存在重大未调整事项或审计范围受限，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <el-dialog v-model="columnDialogVisible" title="F4-2 列设置（源表27列）" width="760px">
      <div class="column-dialog-tip">债权人名称、期末未审余额和审定数为核心列，始终保留；其他列可按当前工作阶段隐藏。</div>
      <el-checkbox-group v-model="visibleColumnProps" class="column-setting-grid">
        <el-checkbox
          v-for="column in allColumns"
          :key="String(column.prop)"
          :value="String(column.prop)"
          :disabled="['creditor', 'closingUnadjusted', 'closingAdjusted'].includes(String(column.prop))"
        >{{ column.label }}</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="resetColumns">恢复全部列</el-button>
        <el-button type="primary" @click="columnDialogVisible = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.f4-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #315a8a;
  border-radius: 4px;
  background: #eef4fa;
}
.guidance-details summary { cursor: pointer; color: #315a8a; font-weight: 600; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert, .risk-alert, .inline-tip { margin-bottom: 10px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
}
.segment-tabs { margin-bottom: 8px; }
.segment-tabs :deep(.el-tabs__content) { display: none; }
.detail-wide-table { width: 100%; }
.detail-wide-table :deep(.el-table__body-wrapper),
.detail-wide-table :deep(.el-scrollbar__wrap) { overflow-x: auto; }
.detail-wide-table :deep(.el-input-number),
.detail-wide-table :deep(.el-select) { width: 100%; }
.formula-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-cell {
  display: inline-block;
  width: 100%;
  color: #315a8a;
  font-weight: 600;
  border-bottom: 1px dashed #b7bcc5;
}
.mismatch-cell { color: #d03050; }
:deep(.auto-calc-col) { background: #f5f7fa !important; }
:deep(.aging-mismatch-row td) { background: #fef0f0 !important; }
:deep(.subsequent-warning-row td) { background: #fdf6ec !important; }
.subtotal-bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px 18px;
  padding: 9px 12px;
  border: 1px solid #dcdfe6;
  border-top: none;
  background: #f3f5f8;
  font-weight: 700;
}
.audit-text-card { margin-top: 16px; border-radius: 8px; }
.audit-text-card :deep(.el-card__header) { padding: 11px 14px; background: #fafafa; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.card-title { font-weight: 600; color: #303133; }
.card-hint { margin-top: 3px; color: #909399; font-size: 12px; }
.card-actions { display: flex; gap: 6px; }
.column-dialog-tip { margin-bottom: 12px; color: #606266; font-size: 12px; }
.column-setting-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 12px;
  max-height: 52vh;
  overflow-y: auto;
}
</style>
