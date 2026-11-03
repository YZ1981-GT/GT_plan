<template>
  <!--
    ReportEquityTable — 权益变动表 el-table 矩阵子组件
    三级表头：本年金额 / 上年金额 > 分组 > 明细列
    GT 紫令牌样式；金额格 ReportMatrixCell（平时 GtAmountCell 文字，editable 时格内编辑、提交发 cell-edit）
    Extracted from ReportView.vue (Task 11.1, report-view-slimdown spec)
  -->
  <el-table
    ref="tableRef"
    :data="rows"
    border
    size="small"
    class="gt-compact-table gt-tb-font-md"
    :span-method="equitySpanMethod"
    :row-class-name="eqRowClassName"
    style="width: 100%"
    :max-height="tableMaxHeight"
    :cell-class-name="cellClassName"
    @cell-click="onCellClick"
    @cell-dblclick="onCellDblClick"
    @cell-contextmenu="onCellContextMenu"
  >
    <el-table-column prop="row_name" label="项目" fixed width="280" :resizable="true">
      <template #default="{ row }">
        <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
      </template>
    </el-table-column>

    <!-- 本年金额 — 动态列（三级表头：本年金额 > 分组 > 明细列） -->
    <el-table-column label="本年金额" header-align="center">
      <el-table-column prop="cy:paid_in_capital" label="实收资本(股本)" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'paid_in_capital', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'paid_in_capital', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column label="其他权益工具" header-align="center">
        <el-table-column prop="cy:other_equity_preferred" label="优先股" width="90" align="right" :resizable="true">
          <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'other_equity_preferred', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'other_equity_preferred', 'current_year', v)" /></template>
        </el-table-column>
        <el-table-column prop="cy:other_equity_perpetual" label="永续债" width="90" align="right" :resizable="true">
          <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'other_equity_perpetual', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'other_equity_perpetual', 'current_year', v)" /></template>
        </el-table-column>
        <el-table-column prop="cy:other_equity_other" label="其他" width="90" align="right" :resizable="true">
          <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'other_equity_other', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'other_equity_other', 'current_year', v)" /></template>
        </el-table-column>
      </el-table-column>
      <el-table-column prop="cy:capital_reserve" label="资本公积" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'capital_reserve', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'capital_reserve', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="cy:treasury_stock" label="减：库存股" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'treasury_stock', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'treasury_stock', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="cy:oci" label="其他综合收益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'oci', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'oci', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="cy:special_reserve" label="专项储备" width="100" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'special_reserve', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'special_reserve', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="cy:surplus_reserve" label="盈余公积" width="100" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'surplus_reserve', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'surplus_reserve', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="cy:general_risk" label="一般风险准备" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'general_risk', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'general_risk', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="cy:retained_earnings" label="未分配利润" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'retained_earnings', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'retained_earnings', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="cy:subtotal" label="小计" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'subtotal', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'subtotal', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="cy:minority" label="少数股东权益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'minority', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'minority', 'current_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="cy:total" label="所有者权益合计" width="120" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'total', 'current_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'total', 'current_year', v)" /></template>
      </el-table-column>
    </el-table-column>

    <!-- 上年金额 — 三级表头（与本年金额结构一致） -->
    <el-table-column label="上年金额" header-align="center">
      <el-table-column prop="py:paid_in_capital" label="实收资本(股本)" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'paid_in_capital', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'paid_in_capital', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column label="其他权益工具" header-align="center">
        <el-table-column prop="py:other_equity_preferred" label="优先股" width="90" align="right" :resizable="true">
          <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'other_equity_preferred', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'other_equity_preferred', 'prior_year', v)" /></template>
        </el-table-column>
        <el-table-column prop="py:other_equity_perpetual" label="永续债" width="90" align="right" :resizable="true">
          <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'other_equity_perpetual', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'other_equity_perpetual', 'prior_year', v)" /></template>
        </el-table-column>
        <el-table-column prop="py:other_equity_other" label="其他" width="90" align="right" :resizable="true">
          <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'other_equity_other', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'other_equity_other', 'prior_year', v)" /></template>
        </el-table-column>
      </el-table-column>
      <el-table-column prop="py:capital_reserve" label="资本公积" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'capital_reserve', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'capital_reserve', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="py:treasury_stock" label="减：库存股" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'treasury_stock', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'treasury_stock', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="py:oci" label="其他综合收益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'oci', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'oci', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="py:special_reserve" label="专项储备" width="100" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'special_reserve', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'special_reserve', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="py:surplus_reserve" label="盈余公积" width="100" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'surplus_reserve', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'surplus_reserve', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="py:general_risk" label="一般风险准备" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'general_risk', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'general_risk', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="py:retained_earnings" label="未分配利润" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'retained_earnings', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'retained_earnings', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="py:subtotal" label="小计" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'subtotal', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'subtotal', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="py:minority" label="少数股东权益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'minority', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'minority', 'prior_year', v)" /></template>
      </el-table-column>
      <el-table-column prop="py:total" label="所有者权益合计" width="120" align="right" :resizable="true">
        <template #default="{ row }"><ReportMatrixCell :value="shown(row, 'total', 'prior_year')" :editable="canEdit(row)" @commit="(v) => onCommit(row, 'total', 'prior_year', v)" /></template>
      </el-table-column>
    </el-table-column>
  </el-table>

  <p v-if="rows.length === 0" class="gt-rv-eq-hint">提示：权益变动表为矩阵结构，各列金额需在项目导入数据后自动填充。</p>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import ReportMatrixCell from './ReportMatrixCell.vue'

type YearKey = 'current_year' | 'prior_year'

// ─── Props ────────────────────────────────────────────────────────────────────
export interface ReportEquityTableProps {
  rows: any[]
  eqColumns: { key: string; label: string }[]
  eqTotalCols: number
  year?: number | null
  tableMaxHeight: number
  cellClassName: (params: any) => string
  fontSize: string
  /** 权益表 span 合并方法 */
  equitySpanMethod: (params: { row: any; column: any; rowIndex: number; columnIndex: number }) => { rowspan: number; colspan: number }
  /** 权益表行样式 */
  eqRowClassName: (params: { row: any }) => string
  /** 权益表取单元格值 */
  eqCellVal: (row: any, colKey: string, yearKey?: 'current_year' | 'prior_year') => any
  /** 是否合并报表（显示少数股东权益/小计列） */
  isConsolidated: boolean
  /** 金额格可格内编辑（未审模式为动态计算、不可改；默认只显示） */
  editable?: boolean
}

const props = defineProps<ReportEquityTableProps>()

// ─── Emits ────────────────────────────────────────────────────────────────────
const emit = defineEmits<{
  (e: 'cell-click', row: any, column: any, cell: HTMLElement, event: MouseEvent): void
  (e: 'cell-dblclick', row: any, column: any): void
  (e: 'cell-contextmenu', row: any, column: any, cell: HTMLElement, event: MouseEvent): void
  /** 格内编辑提交：列键 `cy:` / `py:` + 前端列键（与 `/reports/cell` 的 column_key 一致） */
  (e: 'cell-edit', row: any, columnKey: string, value: number | null, yearKey: YearKey): void
}>()

// ─── 格内编辑（spec excel-style-table-editing 5.4）─────────────────────────────
// 分类行（整行合并成标题）、合计行不可改；提交后到下次取数前先显示刚填的值（保存失败时重新取数即恢复）
const pending = reactive(new Map<string, number | null>())
watch(() => props.rows, () => pending.clear())

function pendingKey(row: any, key: string, yearKey: YearKey): string {
  return `${row?.row_code ?? ''}|${yearKey}|${key}`
}

function canEdit(row: any): boolean {
  // indent_level 0 的非合计行由 equitySpanMethod 合并成整行标题
  return !!props.editable && !!row?.row_code && !row.is_total_row && row.indent_level !== 0
}

function shown(row: any, key: string, yearKey: YearKey): unknown {
  const k = pendingKey(row, key, yearKey)
  return pending.has(k) ? pending.get(k) : props.eqCellVal(row, key, yearKey)
}

function onCommit(row: any, key: string, yearKey: YearKey, value: number | null): void {
  pending.set(pendingKey(row, key, yearKey), value)
  emit('cell-edit', row, `${yearKey === 'prior_year' ? 'py' : 'cy'}:${key}`, value, yearKey)
}

// ─── Event handlers ───────────────────────────────────────────────────────────
function onCellClick(row: any, column: any, cell: HTMLElement, event: MouseEvent) {
  emit('cell-click', row, column, cell, event)
}

function onCellDblClick(row: any, column: any) {
  emit('cell-dblclick', row, column)
}

function onCellContextMenu(row: any, column: any, cell: HTMLElement, event: MouseEvent) {
  emit('cell-contextmenu', row, column, cell, event)
}

// ─── Expose tableRef for drag selection binding ───────────────────────────────
const tableRef = ref<any>(null)
defineExpose({ tableRef })
</script>

<style scoped>
.gt-rv-eq-hint {
  color: var(--gt-color-text-secondary, #999);
  font-size: 12px;
  text-align: center;
  padding: 12px;
}
</style>
