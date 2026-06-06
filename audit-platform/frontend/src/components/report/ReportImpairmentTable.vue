<template>
  <!--
    ReportImpairmentTable — 减值准备表 el-table 矩阵子组件
    含增加/减少嵌套列
    GT 紫令牌样式 + GtAmountCell 统一金额渲染
    Extracted from ReportView.vue (Task 12.1, report-view-slimdown spec)
  -->
  <el-table
    ref="tableRef"
    :data="rows"
    border
    size="small"
    :row-class-name="impRowClassName"
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
    <el-table-column label="年初账面余额" width="130" align="right" :resizable="true">
      <template #default="{ row }">
        <GtAmountCell :value="row.prior_period_amount" />
      </template>
    </el-table-column>
    <!-- 本期增加额 — 嵌套列 -->
    <el-table-column label="本期增加额">
      <el-table-column v-for="col in impIncCols" :key="'inc-' + col.key" :label="col.label" width="110" align="right" :resizable="true">
        <template #default>
          <GtAmountCell :value="0" />
        </template>
      </el-table-column>
    </el-table-column>
    <!-- 本期减少额 — 嵌套列 -->
    <el-table-column label="本期减少额">
      <el-table-column v-for="col in impDecCols" :key="'dec-' + col.key" :label="col.label" width="110" align="right" :resizable="true">
        <template #default>
          <GtAmountCell :value="0" />
        </template>
      </el-table-column>
    </el-table-column>
    <el-table-column label="期末账面余额" width="130" align="right" :resizable="true">
      <template #default="{ row }">
        <GtAmountCell :value="row.current_period_amount" />
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

// ─── Props ────────────────────────────────────────────────────────────────────
export interface ReportImpairmentTableProps {
  rows: any[]
  impIncCols: { key: string; label: string }[]
  impDecCols: { key: string; label: string }[]
  tableMaxHeight: number
  cellClassName: (params: any) => string
  fontSize: string
  /** 减值准备表行样式 */
  impRowClassName: (params: { row: any }) => string
}

const props = defineProps<ReportImpairmentTableProps>()

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
