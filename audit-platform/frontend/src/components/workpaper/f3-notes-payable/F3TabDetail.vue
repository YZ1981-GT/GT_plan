<script setup lang="ts">
/**
 * F3TabDetail — F3-2 明细表（25列→3区段Tab）
 * Spec: .kiro/specs/f3-notes-payable/ Task 6.2
 * 比照 D4TabRevenueDetail（精美组件 gold-standard）
 */
import { computed, toRef, inject, type Ref } from 'vue'
import { useF3Detail, type F3NoteDetailRow, type F3DetailColumn } from '../composables/useF3Detail'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
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
  searchQuery,
  addRow,
  removeRow,
  updateCell,
  rowClassName,
  basicColumns,
  infoColumns,
  auditColumns,
} = useF3Detail({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const activeColumns = computed<F3DetailColumn[]>(() => {
  if (activeSegment.value === 'basic') return basicColumns
  if (activeSegment.value === 'detail') return infoColumns
  return auditColumns
})

const DETAIL_SCROLL_THRESHOLD = 50
const useDetailScroll = computed(() => filteredRows.value.length > DETAIL_SCROLL_THRESHOLD)

function isFormulaCol(col: F3DetailColumn): boolean {
  return !!col.formula || ['termDays', 'overdueDays', 'closingBalance', 'adjustedBalance', 'isOverdue'].includes(col.prop as string)
}

function displayValue(row: F3NoteDetailRow, prop: string): string {
  const v = (row as any)[prop]
  if (typeof v === 'number') return fmtAmount(v)
  return v ?? ''
}
</script>

<template>
  <div class="f3-tab-detail">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐张登记应付票据明细：出票人、收票人、票据种类（银行承兑/商业承兑）、面值、出票日、到期日、承兑行、保证金比例等。</p>
        <p>2. 25 列拆为 3 区段 Tab（基础信息 / 票据详情 / 审定调整），区段间行同步；灰底虚线列为公式列（票据期限、逾期天数、期末余额、审定余额），不可手工编辑。</p>
        <p>3. 逾期天数&gt;0 行橙色高亮，关注已到期未兑付票据是否应转应付账款并追加利息/罚息。</p>
        <p>4. 期末余额合计应与 F3-1 审定表、试算平衡表科目2201 核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：应付票据明细真实存在、记录完整，票据种类与到期状态分类准确，为审定表与逾期检查提供明细支撑。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-input v-model="searchQuery" placeholder="搜索出票人/收票人..." size="small" clearable style="width:200px" />
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
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
        <el-tag size="small" type="info">共 {{ filteredRows.length }} 行</el-tag>
      </div>
    </div>

    <el-tabs v-model="activeSegment" type="border-card" class="segment-tabs">
      <el-tab-pane name="basic" label="基础信息(9列)" />
      <el-tab-pane name="detail" label="票据详情(8列)" />
      <el-tab-pane name="audit" label="审定调整(8列)" />
    </el-tabs>

    <div v-if="useDetailScroll" class="scroll-hint">共 {{ filteredRows.length }} 行 · 固定表头滚动</div>

    <el-table
      :data="filteredRows"
      border
      size="small"
      :row-class-name="rowClassName"
      :max-height="useDetailScroll ? 480 : undefined"
      style="width: 100%; margin-top: 8px"
    >
      <el-table-column
        v-for="col in activeColumns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth || 100"
        :class-name="isFormulaCol(col) ? 'auto-calc-col' : ''"
      >
        <template #header>
          <el-tooltip v-if="col.formula" :content="col.formula" placement="top">
            <span class="formula-header">{{ col.label }}</span>
          </el-tooltip>
          <span v-else>{{ col.label }}</span>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="col.editable && !isReadonly && col.prop !== 'seq'"
            :model-value="(row as any)[col.prop]"
            size="small"
            @change="(v: any) => updateCell(row.rowId, col.prop as string, v)"
          />
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
      合计 — 面值: {{ fmtAmount(subtotalRow.faceValue) }} |
      期末余额: {{ fmtAmount(subtotalRow.closingBalance) }} |
      审定余额: {{ fmtAmount(subtotalRow.adjustedBalance) }}
    </div>
  </div>
</template>

<style scoped>
.f3-tab-detail {
  padding: 12px;
}
.f3-tab-detail :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.f3-tab-detail :deep(.el-table .cell) {
  font-size: 13px !important;
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
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
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
</style>
