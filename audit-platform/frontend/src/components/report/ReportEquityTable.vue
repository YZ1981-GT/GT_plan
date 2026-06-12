<template>
  <!--
    ReportEquityTable — 权益变动表 el-table 矩阵子组件
    三级表头：本年金额 / 上年金额 > 分组 > 明细列
    GT 紫令牌样式 + GtAmountCell 统一金额渲染
    Extracted from ReportView.vue (Task 11.1, report-view-slimdown spec)
  -->
  <el-table
    ref="tableRef"
    :data="rows"
    border
    size="small"
    :span-method="equitySpanMethod"
    :row-class-name="eqRowClassName"
    style="width: 100%"
    :max-height="tableMaxHeight"
    :style="{ fontSize }"
    :cell-class-name="cellClassName"
    @cell-click="onCellClick"
    @cell-dblclick="onCellDblClick"
    @cell-contextmenu="onCellContextMenu"
    :header-cell-style="{ background: '#f8f6fb', color: '#333', whiteSpace: 'nowrap', fontSize: '12px' }"
  >
    <el-table-column prop="row_name" label="项目" fixed width="280" :resizable="true">
      <template #default="{ row }">
        <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
      </template>
    </el-table-column>

    <!-- 本年金额 — 动态列（三级表头：本年金额 > 分组 > 明细列） -->
    <el-table-column label="本年金额" header-align="center">
      <el-table-column prop="cy:paid_in_capital" label="实收资本(股本)" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'paid_in_capital')" /></template>
      </el-table-column>
      <el-table-column label="其他权益工具" header-align="center">
        <el-table-column prop="cy:other_equity_preferred" label="优先股" width="90" align="right" :resizable="true">
          <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_preferred')" /></template>
        </el-table-column>
        <el-table-column prop="cy:other_equity_perpetual" label="永续债" width="90" align="right" :resizable="true">
          <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_perpetual')" /></template>
        </el-table-column>
        <el-table-column prop="cy:other_equity_other" label="其他" width="90" align="right" :resizable="true">
          <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_other')" /></template>
        </el-table-column>
      </el-table-column>
      <el-table-column prop="cy:capital_reserve" label="资本公积" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'capital_reserve')" /></template>
      </el-table-column>
      <el-table-column prop="cy:treasury_stock" label="减：库存股" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'treasury_stock')" /></template>
      </el-table-column>
      <el-table-column prop="cy:oci" label="其他综合收益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'oci')" /></template>
      </el-table-column>
      <el-table-column prop="cy:special_reserve" label="专项储备" width="100" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'special_reserve')" /></template>
      </el-table-column>
      <el-table-column prop="cy:surplus_reserve" label="盈余公积" width="100" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'surplus_reserve')" /></template>
      </el-table-column>
      <el-table-column prop="cy:general_risk" label="一般风险准备" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'general_risk')" /></template>
      </el-table-column>
      <el-table-column prop="cy:retained_earnings" label="未分配利润" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'retained_earnings')" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="cy:subtotal" label="小计" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'subtotal')" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="cy:minority" label="少数股东权益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'minority')" /></template>
      </el-table-column>
      <el-table-column prop="cy:total" label="所有者权益合计" width="120" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'total')" /></template>
      </el-table-column>
    </el-table-column>

    <!-- 上年金额 — 三级表头（与本年金额结构一致） -->
    <el-table-column label="上年金额" header-align="center">
      <el-table-column prop="py:paid_in_capital" label="实收资本(股本)" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'paid_in_capital', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column label="其他权益工具" header-align="center">
        <el-table-column prop="py:other_equity_preferred" label="优先股" width="90" align="right" :resizable="true">
          <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_preferred', 'prior_year')" /></template>
        </el-table-column>
        <el-table-column prop="py:other_equity_perpetual" label="永续债" width="90" align="right" :resizable="true">
          <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_perpetual', 'prior_year')" /></template>
        </el-table-column>
        <el-table-column prop="py:other_equity_other" label="其他" width="90" align="right" :resizable="true">
          <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'other_equity_other', 'prior_year')" /></template>
        </el-table-column>
      </el-table-column>
      <el-table-column prop="py:capital_reserve" label="资本公积" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'capital_reserve', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column prop="py:treasury_stock" label="减：库存股" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'treasury_stock', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column prop="py:oci" label="其他综合收益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'oci', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column prop="py:special_reserve" label="专项储备" width="100" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'special_reserve', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column prop="py:surplus_reserve" label="盈余公积" width="100" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'surplus_reserve', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column prop="py:general_risk" label="一般风险准备" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'general_risk', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column prop="py:retained_earnings" label="未分配利润" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'retained_earnings', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="py:subtotal" label="小计" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'subtotal', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column v-if="isConsolidated" prop="py:minority" label="少数股东权益" width="110" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'minority', 'prior_year')" /></template>
      </el-table-column>
      <el-table-column prop="py:total" label="所有者权益合计" width="120" align="right" :resizable="true">
        <template #default="{ row }"><GtAmountCell :value="eqCellVal(row, 'total', 'prior_year')" /></template>
      </el-table-column>
    </el-table-column>
  </el-table>

  <p v-if="rows.length === 0" class="gt-rv-eq-hint">提示：权益变动表为矩阵结构，各列金额需在项目导入数据后自动填充。</p>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

// ─── Props ────────────────────────────────────────────────────────────────────
export interface ReportEquityTableProps {
  rows: any[]
  eqColumns: { key: string; label: string }[]
  eqTotalCols: number
  year: number
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
}

const props = defineProps<ReportEquityTableProps>()

// ─── Emits ────────────────────────────────────────────────────────────────────
const emit = defineEmits<{
  (e: 'cell-click', row: any, column: any, cell: HTMLElement, event: MouseEvent): void
  (e: 'cell-dblclick', row: any, column: any): void
  (e: 'cell-contextmenu', row: any, column: any, cell: HTMLElement, event: MouseEvent): void
}>()

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
