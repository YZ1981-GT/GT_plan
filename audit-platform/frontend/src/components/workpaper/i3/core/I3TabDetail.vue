<template>
  <div class="i3-tab-detail">
    <!-- 方法论上下文（琥珀色左边线） -->
    <div class="methodology-context">
      <p><strong>I3-2 商誉明细表 — 3区段Tab使用说明：</strong></p>
      <p>本表30列按功能拆分为3个区段Tab切换查看，切换Tab时当前选中行保持同步高亮。</p>
      <p>① 基础：被投资单位/并购日期/对价/被购方净资产/持股比例/控制类型/合并方式/股权层级/行业</p>
      <p>② 入账：合并成本/可辨认净资产公允/商誉原值(公式)/少数股东权益/成本明细/评估方法</p>
      <p>③ 减值：累计减值期初/本期减值/累计减值期末(公式)/商誉净值(公式)/所属CGU/可收回金额/测试方法</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：逐被投资单位核实商誉的初始确认（合并成本−可辨认净资产公允价值份额）、累计减值及净值的真实性与准确性；核对商誉分摊至资产组(CGU)的合理性；明细合计与 I3-1 审定表勾稽一致（CAS8、CAS20）。"
    />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <ul>
          <li>商誉原值 = 合并成本 − 可辨认净资产公允价值份额（CAS20 非同一控制下企业合并）。</li>
          <li>商誉不摊销，累计减值期末 = 累计减值期初 + 本期减值；商誉净值 = 原值 − 累计减值。</li>
          <li>每项商誉须分摊至预期受益的资产组(CGU)，分摊层级不高于经营分部（CAS8 第十八条）。</li>
          <li>本表 30 列按"基础 / 入账 / 减值"三区段切换查看，行选中在各区段间保持同步。</li>
          <li>明细合计须与 I3-1 审定表商誉原值 / 累计减值 / 净值一致，差异需查明。</li>
        </ul>
      </div>
    </details>

    <!-- 交叉验证警告（黄色alert） -->
    <el-alert
      v-if="crossValidation.hasAnyWarning"
      type="warning"
      :closable="false"
      class="cross-validation-alert"
    >
      <template #default>
        <div class="cross-validation-content">
          <span>明细表合计与I3-1审定表不一致：</span>
          <span v-if="crossValidation.hasOriginalWarning" class="warning-item">
            商誉原值差异 {{ fmtAmount(crossValidation.goodwillOriginalDiff) }}
          </span>
          <span v-if="crossValidation.hasImpairmentWarning" class="warning-item">
            累计减值差异 {{ fmtAmount(crossValidation.accImpairmentDiff) }}
          </span>
          <span v-if="crossValidation.hasNetValueWarning" class="warning-item">
            净值差异 {{ fmtAmount(crossValidation.netValueDiff) }}
          </span>
        </div>
      </template>
    </el-alert>

    <!-- 区段Tab切换（el-segmented） -->
    <div class="toolbar-row tab-toolbar">
      <el-segmented
        v-model="activeSectionKey"
        :options="segmentOptions"
        class="segment-bar"
      />

      <div class="toolbar-right">
        <GtIndexChip value="wp:I3-2" :context-project-id="projectId" />
        <el-button
          v-if="!isReadonly"
          type="primary"
          size="small"
          @click="handleAddRow"
        >
          + 新增
        </el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" class="import-export-dropdown">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="row-count">共 {{ rows.length }} 行</span>
      </div>
    </div>

    <!-- 数据表格（根据 activeSection 列渲染） -->
    <el-table
      :data="rows"
      border
      size="small"
      highlight-current-row
      :current-row-key="activeRowKey"
      row-key="rowId"
      class="detail-table"
      :row-class-name="getRowClassName"
      max-height="480"
      @current-change="onCurrentRowChange"
    >
      <!-- 序号列 -->
      <el-table-column type="index" label="#" width="45" align="center" fixed="left" />

      <!-- 动态列 -->
      <el-table-column
        v-for="col in activeColumns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :min-width="col.width"
        :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
      >
        <!-- 公式列表头带tooltip -->
        <template v-if="col.type === 'formula'" #header>
          <el-tooltip :content="col.tooltip" placement="top">
            <span class="formula-col-header">{{ col.label }}</span>
          </el-tooltip>
        </template>

        <!-- 单元格渲染 -->
        <template #default="{ row, $index }">
          <!-- 公式列：虚线下划线 + 只读 -->
          <span v-if="col.type === 'formula'" class="formula-value">
            <el-tooltip :content="col.tooltip" placement="top">
              <span>{{ fmtAmount((row as any)[col.key]) }}</span>
            </el-tooltip>
          </span>

          <!-- 数字可编辑列 -->
          <el-input-number
            v-else-if="col.type === 'number' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            size="small"
            :controls="false"
            :precision="2"
            class="cell-input-number"
            @change="(val: number | undefined) => handleCellChange($index, col.key, val ?? 0)"
          />

          <!-- 文本可编辑列 -->
          <el-input
            v-else-if="col.type === 'text' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            size="small"
            class="cell-input-text"
            @change="(val: string) => handleCellChange($index, col.key, val)"
          />

          <!-- 日期可编辑列 -->
          <el-date-picker
            v-else-if="col.type === 'date' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            class="cell-date-picker"
            @change="(val: string) => handleCellChange($index, col.key, val)"
          />

          <!-- 下拉选择可编辑列 -->
          <el-select
            v-else-if="col.type === 'select' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            size="small"
            class="cell-select"
            @change="(val: string) => handleCellChange($index, col.key, val)"
          >
            <el-option
              v-for="opt in col.options"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>

          <!-- 只读列（非公式） -->
          <span v-else class="cell-readonly">
            {{ col.type === 'number' ? fmtAmount((row as any)[col.key]) : (row as any)[col.key] || '-' }}
          </span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="80" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text @click="handleRemoveRow($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行（sticky高亮） -->
    <div class="summary-section">
      <el-table
        :data="[summaryDisplayRow]"
        border
        size="small"
        class="summary-table"
      >
        <el-table-column label="#" width="45" align="center">
          <template #default>
            <span class="summary-label">合计</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="col in activeColumns"
          :key="'sum-' + col.key"
          :prop="col.key"
          :label="col.label"
          :min-width="col.width"
          :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
        >
          <template #default="{ row }">
            <span class="summary-value">
              {{ getSummaryValue(row, col) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="80" />
      </el-table>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="记录商誉明细的审计说明（如各被投资单位商誉来源、分摊至CGU的依据、评估方法等）..."
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="记录商誉明细的审计结论（如：商誉明细列示完整、初始确认与减值计价准确，与审定表勾稽一致）..."
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabDetail.vue — I3-2 商誉明细表（30列3区段Tab）
 *
 * 30列拆为3区段Tab：基础 | 入账 | 减值
 * el-segmented切换 + 行同步 + 公式列虚线tooltip + 合计行sticky + 交叉验证
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 4.3
 * Requirements: 3.1-3.4
 */
import { computed, toRef, watch, ref, type Ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'
import {
  useI3Detail,
  type I3DetailRow,
  type I3DetailSection,
  I3_DETAIL_SECTION_LABELS,
} from '../../composables/useI3Detail'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** 审定表商誉原值小计（交叉验证用） */
  adjGoodwillOriginalSubtotal?: number
  /** 审定表累计减值小计（交叉验证用） */
  adjAccImpairmentSubtotal?: number
  /** 审定表净值小计（交叉验证用） */
  adjNetValueSubtotal?: number
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  activeSection,
  activeRowIndex,
  summaryRow,
  crossValidation,
  activeColumns,
  sections,
  switchSection,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
} = useI3Detail(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'allResponses') as Ref<Map<string, any>>,
  {
    adjGoodwillOriginalSubtotal: toRef(props, 'adjGoodwillOriginalSubtotal') as Ref<number>,
    adjAccImpairmentSubtotal: toRef(props, 'adjAccImpairmentSubtotal') as Ref<number>,
    adjNetValueSubtotal: toRef(props, 'adjNetValueSubtotal') as Ref<number>,
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── el-segmented 选项 ───────────────────────────────────────────────────────

/** el-segmented选项配置 */
const segmentOptions = I3_DETAIL_SECTION_LABELS.map((label, idx) => ({
  label,
  value: idx as I3DetailSection,
}))

/** el-segmented绑定的v-model值 */
const activeSectionKey = computed({
  get: () => activeSection.value,
  set: (val: I3DetailSection) => switchSection(val),
})

// ─── Computed ────────────────────────────────────────────────────────────────

/** 当前选中行的rowKey（供el-table current-row-key） */
const activeRowKey = computed(() => {
  if (activeRowIndex.value < 0 || activeRowIndex.value >= rows.value.length) return ''
  return rows.value[activeRowIndex.value]?.rowId ?? ''
})

/** 合计行展示数据（根据当前Section） */
const summaryDisplayRow = computed(() => {
  const s = summaryRow.value
  const sec = activeSection.value
  switch (sec) {
    case 0: // 基础
      return {
        investee: '合计',
        acquisitionDate: '',
        consideration: s.consideration,
        counterpartyNetAsset: s.counterpartyNetAsset,
        shareholding: '',
        controlType: '',
        mergerType: '',
        equityLevel: '',
        industry: '',
        basicRemark: '',
      }
    case 1: // 入账
      return {
        investee: '合计',
        mergerCost: s.mergerCost,
        netAssetFairValue: s.netAssetFairValue,
        goodwillOriginal: s.goodwillOriginal,
        minorityInterest: s.minorityInterest,
        costConsideration: s.costConsideration,
        costContingent: s.costContingent,
        costTransactionFee: s.costTransactionFee,
        mergerDate: '',
        valuationBaseDate: '',
        valuationMethod: '',
        valuationAppreciation: '',
      }
    case 2: // 减值
      return {
        investee: '合计',
        accImpairmentBegin: s.accImpairmentBegin,
        currentImpairment: s.currentImpairment,
        accImpairmentEnd: s.accImpairmentEnd,
        goodwillNetValue: s.goodwillNetValue,
        cguName: '',
        recoverableAmount: s.recoverableAmount,
        impairmentTestDate: '',
        impairmentTestMethod: '',
        impairmentIndicator: '',
      }
    default:
      return {}
  }
})

// ─── Event Handlers ──────────────────────────────────────────────────────────

/** 行点击同步（跨Tab高亮保持） */
function onCurrentRowChange(row: I3DetailRow | null): void {
  if (!row) return
  const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) setActiveRow(idx)
}

/** 单元格值变化 → 自动重算公式列 + 持久化 */
function handleCellChange(rowIndex: number, field: string, value: string | number): void {
  updateCell(rowIndex, field as keyof I3DetailRow, value)
}

/** 新增行：弹ElMessageBox.prompt输入被投资单位名称 */
async function handleAddRow(): Promise<void> {
  await addRow()
}

/** 删除行 */
function handleRemoveRow(index: number): void {
  removeRow(index)
}

/** 导出模板（委托useI3ImportExport） */
function handleExportTemplate(): void {
  console.log('[I3-Detail] Export template — 委托 useI3ImportExport')
}

/** 导出数据 */
function handleExportData(): void {
  console.log('[I3-Detail] Export data — 委托 useI3ImportExport')
}

/** 导入数据 */
function handleImportData(): void {
  console.log('[I3-Detail] Import data — 委托 useI3ImportExport')
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ rowIndex }: { row: I3DetailRow; rowIndex: number }): string {
  return rowIndex === activeRowIndex.value ? 'active-synced-row' : ''
}

// ─── Summary Value Helper ────────────────────────────────────────────────────

/** 获取合计行单元格显示值 */
function getSummaryValue(row: Record<string, any>, col: { key: string; type: string }): string {
  const val = row[col.key]
  if (val == null || val === '') return '-'
  if (col.type === 'number' || col.type === 'formula') return fmtAmount(val as number)
  return String(val)
}

// ─── 审计说明 / 审计结论（纯文本，无AI） ─────────────────────────────────────
const NOTE_KEY = 'I3-2-audit-note'
const CONCLUSION_KEY = 'I3-2-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', CONCLUSION_KEY, val)
}

watch(
  () => props.allResponses,
  () => {
    const n = props.allResponses.get(NOTE_KEY)
    if (n?.remark != null) auditNote.value = n.remark
    const c = props.allResponses.get(CONCLUSION_KEY)
    if (c?.remark != null) auditConclusion.value = c.remark
  },
  { immediate: true },
)
</script>

<style scoped>
.i3-tab-detail {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

/* 方法论上下文（琥珀色） */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p {
  margin: 0;
}
.methodology-context strong {
  color: #78350f;
}

/* 交叉验证警告 */
.cross-validation-alert {
  margin-bottom: 12px;
}
.cross-validation-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.warning-item {
  padding: 2px 8px;
  background: #fef9c3;
  border-radius: 4px;
  font-weight: 500;
}

/* 工具栏行：segmented左 + 按钮右 */
.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 16px;
  flex-wrap: wrap;
}
.segment-bar {
  flex-shrink: 0;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.import-export-dropdown {
  margin-left: 0;
}
.row-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

/* 明细表格 */
.detail-table {
  font-size: var(--wp-font-size, 13px);
}
.detail-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f8fafc;
}
.detail-table :deep(.active-synced-row) {
  background: #eff6ff !important;
}
.detail-table :deep(.el-table__body tr:hover > td) {
  background: #f0f9ff;
}

/* 公式列表头：虚线下划线 + cursor:help */
.formula-col-header {
  border-bottom: 1px dashed #6b7280;
  cursor: help;
  padding-bottom: 1px;
}

/* 公式值：虚线下划线 + cursor:help + tooltip来源 */
.formula-value {
  border-bottom: 1px dashed #9ca3af;
  cursor: help;
  color: #374151;
  font-weight: 500;
}

/* 输入控件 */
.cell-input-number {
  width: 100%;
}
.cell-input-number :deep(.el-input__inner) {
  text-align: right;
}
.cell-input-text {
  width: 100%;
}
.cell-date-picker {
  width: 100%;
}
.cell-select {
  width: 100%;
}
.cell-readonly {
  color: var(--el-text-color-regular);
}

/* 合计行区域（sticky高亮） */
.summary-section {
  margin-top: 8px;
  position: sticky;
  bottom: 0;
  z-index: 5;
}
.summary-table {
  font-size: var(--wp-font-size, 13px);
}
.summary-table :deep(.el-table__header) {
  display: none;
}
.summary-table :deep(tr td) {
  background: #f0fdf4 !important;
  font-weight: 600;
}
.summary-label {
  font-weight: 700;
  color: #166534;
}
.summary-value {
  font-weight: 600;
  color: #166534;
}

/* 审计目标 alert */
.objective-alert {
  margin-bottom: 12px;
}

/* 编制提示 details */
.guidance-details {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
}
.guidance-details .guidance-content ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}

/* 审计说明/结论卡片 */
.audit-note-card {
  margin-top: 12px;
}
</style>
