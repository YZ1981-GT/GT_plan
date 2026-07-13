<template>
  <div class="i1-tab-detail">
    <!-- 方法论上下文（琥珀色左边线） -->
    <div class="methodology-context">
      <p><strong>I1-2 无形资产明细表 — 4区段Tab使用说明：</strong></p>
      <p>本表56列按功能拆分为4个区段Tab切换查看，切换Tab时当前选中行保持同步高亮。</p>
      <p>① 基础信息：资产分类/名称/取得日期/使用寿命/残值率/摊销方法</p>
      <p>② 原值变动：期初原值/本期增加/本期减少/期末原值（公式自动计算）</p>
      <p>③ 摊销：摊销期初/本期摊销/摊销转出/摊销期末/净值（公式自动计算）</p>
      <p>④ 减值：减值期初/本期计提/本期转回/减值期末（公式自动计算）</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实无形资产各项目分类、原值、摊销、减值明细登记的完整、准确，并与审定表 I1 三科目小计勾稽一致。"
      class="objective-alert"
    />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐项登记无形资产明细，资产分类与摊销方法应与被审计单位会计政策一致（CAS6）。</p>
        <p>2. 原值期末=期初+增加-减少；累计摊销期末=期初+本期摊销-转出；减值期末=期初+计提-转回；净值=原值期末-摊销期末-减值期末（灰底列自动计算）。</p>
        <p>3. "摊销原值"列即原值期末，作为摊销测算(I1-10/I1-11)的计算基数，来源"原值变动"区段。</p>
        <p>4. 明细合计应与审定表 I1 原值/摊销/减值小计勾稽一致，差异超过阈值将黄色告警。</p>
      </div>
    </details>

    <!-- 交叉验证警告 -->
    <div v-if="crossValidation.hasAnyWarning" class="cross-validation-warning">
      <el-icon class="warning-icon"><WarningFilled /></el-icon>
      <span>明细表合计与I1审定表小计不一致：</span>
      <span v-if="crossValidation.hasCostWarning" class="warning-item">
        原值差异 {{ fmtAmount(crossValidation.costDiff) }}
      </span>
      <span v-if="crossValidation.hasAmortWarning" class="warning-item">
        摊销差异 {{ fmtAmount(crossValidation.amortDiff) }}
      </span>
      <span v-if="crossValidation.hasImpairWarning" class="warning-item">
        减值差异 {{ fmtAmount(crossValidation.impairDiff) }}
      </span>
    </div>

    <!-- 工具栏：新增行 + 导入导出 -->
    <div class="tab-toolbar">
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
      <span class="chip-wrap"><GtIndexChip value="wp:I1-2" :context-project-id="projectId" /></span>
      <span class="row-count">共 {{ rows.length }} 行</span>
    </div>

    <!-- 4区段Tab切换 -->
    <el-tabs v-model="activeTab" type="border-card" class="segment-tabs" @tab-change="onTabChange">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.key"
        :label="tab.label"
        :name="tab.key"
      >
        <!-- 每区段对应的el-table -->
        <el-table
          :data="rows"
          border
          size="small"
          highlight-current-row
          :current-row-key="activeRowKey"
          row-key="rowId"
          class="detail-table"
          :row-class-name="getRowClassName"
          @current-change="onCurrentRowChange"
        >
          <!-- 序号列 -->
          <el-table-column type="index" label="#" width="50" align="center" />

          <!-- 动态列 -->
          <el-table-column
            v-for="col in tab.columns"
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
              <span
                v-if="col.type === 'formula'"
                class="formula-value"
              >
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
          <el-table-column v-if="!isReadonly" label="操作" width="100" align="center" fixed="right">
            <template #default="{ $index }">
              <el-button size="small" type="danger" text @click="handleRemoveRow($index)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 合计行（不可编辑） -->
        <div class="summary-section">
          <el-table
            :data="[summaryDisplayRow(tab.key)]"
            border
            size="small"
            class="summary-table"
          >
            <el-table-column label="#" width="50" align="center">
              <template #default>
                <span class="summary-label">合计</span>
              </template>
            </el-table-column>
            <el-table-column
              v-for="col in tab.columns"
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
            <el-table-column v-if="!isReadonly" label="" width="100" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：明细取数与登记情况、与审定表勾稽核对结果、异常项处理等。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除下列事项应予调整外，其余未见异常。C、存在重大未调整事项，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, watch, type Ref } from 'vue'
import { ArrowDown, WarningFilled } from '@element-plus/icons-vue'
import { useI1Detail, type I1DetailTab, type I1DetailRow } from '../../composables/useI1Detail'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  adjCostSubtotal?: number
  adjAmortSubtotal?: number
  adjImpairSubtotal?: number
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────────

const NOTE_KEY = 'I1-2-audit-note'
const CONCLUSION_KEY = 'I1-2-audit-conclusion'
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

function loadAuditText(): void {
  const n = props.allResponses.get(NOTE_KEY)
  if (n) auditNote.value = (n.remark ?? n.conclusion ?? '') as string
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c) auditConclusion.value = (c.remark ?? c.conclusion ?? '') as string
}

onMounted(loadAuditText)
watch(() => props.allResponses, loadAuditText, { deep: true })

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  activeTab,
  activeRowIndex,
  summaryRow,
  crossValidation,
  tabs,
  switchTab,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
} = useI1Detail(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'allResponses') as Ref<Map<string, any>>,
  {
    adjCostSubtotal: toRef(props, 'adjCostSubtotal') as Ref<number>,
    adjAmortSubtotal: toRef(props, 'adjAmortSubtotal') as Ref<number>,
    adjImpairSubtotal: toRef(props, 'adjImpairSubtotal') as Ref<number>,
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── Computed ────────────────────────────────────────────────────────────────

/** 当前选中行的rowKey（供el-table current-row-key） */
const activeRowKey = computed(() => {
  if (activeRowIndex.value < 0 || activeRowIndex.value >= rows.value.length) return ''
  return rows.value[activeRowIndex.value]?.rowId ?? ''
})

// ─── Event Handlers ──────────────────────────────────────────────────────────

/** Tab切换，保持行同步 */
function onTabChange(tabKey: string | number): void {
  switchTab(tabKey as I1DetailTab)
}

/** 行点击同步（跨Tab高亮保持） */
function onCurrentRowChange(row: I1DetailRow | null): void {
  if (!row) return
  const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) setActiveRow(idx)
}

/** 单元格值变化 → 自动重算公式列 + 持久化 */
function handleCellChange(rowIndex: number, field: string, value: string | number): void {
  updateCell(rowIndex, field as keyof I1DetailRow, value)
}

/** 新增行：弹ElMessageBox.prompt输入名称 */
async function handleAddRow(): Promise<void> {
  await addRow()
}

/** 删除行 */
function handleRemoveRow(index: number): void {
  removeRow(index)
}

/** 导出模板（委托useI1ImportExport） */
function handleExportTemplate(): void {
  console.log('[I1-Detail] Export template — 委托 useI1ImportExport')
}

/** 导出数据（委托useI1ImportExport） */
function handleExportData(): void {
  console.log('[I1-Detail] Export data — 委托 useI1ImportExport')
}

/** 导入数据（委托useI1ImportExport） */
function handleImportData(): void {
  console.log('[I1-Detail] Import data — 委托 useI1ImportExport')
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ rowIndex }: { row: I1DetailRow; rowIndex: number }): string {
  return rowIndex === activeRowIndex.value ? 'active-synced-row' : ''
}

// ─── Summary Row Display ─────────────────────────────────────────────────────

/** 根据当前Tab返回合计行的展示数据对象 */
function summaryDisplayRow(tabKey: I1DetailTab): Record<string, any> {
  const s = summaryRow.value
  switch (tabKey) {
    case 'basic':
      return { category: '—', name: '合计', acquisitionDate: '', usefulLifeMonths: '', salvageRate: '', amortizationMethod: '' }
    case 'cost':
      return { name: '合计', costBegin: s.costBegin, costIncrease: s.costIncrease, costDecrease: s.costDecrease, costEnd: s.costEnd }
    case 'amort':
      return { name: '合计', costEnd: s.costEnd, accAmortBegin: s.accAmortBegin, amortProvision: s.amortProvision, amortTransferOut: s.amortTransferOut, accAmortEnd: s.accAmortEnd, netValue: s.netValue }
    case 'impairment':
      return { name: '合计', impairmentBegin: s.impairmentBegin, impairmentProvision: s.impairmentProvision, impairmentReversal: s.impairmentReversal, impairmentEnd: s.impairmentEnd }
    default:
      return {}
  }
}

/** 获取合计行单元格显示值 */
function getSummaryValue(row: Record<string, any>, col: { key: string; type: string }): string {
  const val = row[col.key]
  if (val == null || val === '') return '-'
  if (col.type === 'number' || col.type === 'formula') return fmtAmount(val as number)
  return String(val)
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-detail {
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

/* 审计目标 alert */
.objective-alert { margin-bottom: 12px; }

/* 编制提示 details */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

/* 索引 chip */
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计说明/结论卡片 */
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

/* 交叉验证警告（黄色） */
.cross-validation-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 6px;
  font-size: 12px;
  color: #854d0e;
}
.warning-icon {
  color: #eab308;
  font-size: 16px;
}
.warning-item {
  padding: 2px 8px;
  background: #fef9c3;
  border-radius: 4px;
  font-weight: 500;
  margin-left: 4px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.import-export-dropdown {
  margin-left: auto;
}
.row-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

/* 4区段Tab */
.segment-tabs {
  border-radius: 8px;
}
.segment-tabs :deep(.el-tabs__header) {
  background: #f8fafc;
}
.segment-tabs :deep(.el-tabs__item) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
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

/* 合计行区域 */
.summary-section {
  margin-top: 8px;
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
</style>
