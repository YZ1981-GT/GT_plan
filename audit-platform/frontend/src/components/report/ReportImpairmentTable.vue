<template>
  <!--
    ReportImpairmentTable — 减值准备表 el-table 矩阵子组件
    含增加/减少嵌套列
    GT 紫令牌样式；金额格 ReportMatrixCell（本期增减各列 editable 时格内编辑、提交发 cell-edit）
    Extracted from ReportView.vue (Task 12.1, report-view-slimdown spec)
  -->
  <el-table
    ref="tableRef"
    :data="rows"
    border
    size="small"
    class="gt-compact-table gt-tb-font-md"
    :row-class-name="impRowClassName"
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
    <el-table-column label="年初账面余额" width="130" align="right" :resizable="true">
      <template #default="{ row }">
        <ReportMatrixCell :value="impVal(row, 'opening_balance')" />
      </template>
    </el-table-column>
    <!-- 本期增加额 — 嵌套列（合计列按本组各列求和、不可改） -->
    <el-table-column label="本期增加额">
      <el-table-column v-for="col in impIncCols" :key="'inc-' + col.key" :label="col.label" width="110" align="right" :resizable="true">
        <template #default="{ row }">
          <ReportMatrixCell :value="col.sum ? groupSum(row, impIncCols) : impVal(row, col.key)" :editable="!col.sum && canEdit(row)" @commit="(v) => onCommit(row, col.key, v)" />
        </template>
      </el-table-column>
    </el-table-column>
    <!-- 本期减少额 — 嵌套列 -->
    <el-table-column label="本期减少额">
      <el-table-column v-for="col in impDecCols" :key="'dec-' + col.key" :label="col.label" width="110" align="right" :resizable="true">
        <template #default="{ row }">
          <ReportMatrixCell :value="col.sum ? groupSum(row, impDecCols) : impVal(row, col.key)" :editable="!col.sum && canEdit(row)" @commit="(v) => onCommit(row, col.key, v)" />
        </template>
      </el-table-column>
    </el-table-column>
    <el-table-column label="期末账面余额" width="130" align="right" :resizable="true">
      <template #default="{ row }">
        <ReportMatrixCell :value="impVal(row, 'closing_balance')" />
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import ReportMatrixCell from './ReportMatrixCell.vue'

/** 列键 = 导出模板 `{{imp:CODE:列键}}` 的列键；`sum` 为本组合计（按本组各列求和、不可改） */
export interface ImpColumn { key: string; label: string; sum?: boolean }

// ─── Props ────────────────────────────────────────────────────────────────────
export interface ReportImpairmentTableProps {
  rows: any[]
  impIncCols: ImpColumn[]
  impDecCols: ImpColumn[]
  tableMaxHeight: number
  cellClassName: (params: any) => string
  fontSize: string
  /** 减值准备表行样式 */
  impRowClassName: (params: { row: any }) => string
  /** 本期增减各列可格内编辑（未审模式为动态计算、不可改；默认只显示） */
  editable?: boolean
}

const props = defineProps<ReportImpairmentTableProps>()

// ─── Emits ────────────────────────────────────────────────────────────────────
const emit = defineEmits<{
  (e: 'cell-click', row: any, column: any, cell: HTMLElement, event: MouseEvent): void
  (e: 'cell-dblclick', row: any, column: any): void
  (e: 'cell-contextmenu', row: any, column: any, cell: HTMLElement, event: MouseEvent): void
  /** 格内编辑提交：列键同导出模板（与 `/reports/cell` 的 column_key 一致） */
  (e: 'cell-edit', row: any, columnKey: string, value: number | null): void
}>()

// ─── 取值与格内编辑（spec excel-style-table-editing 5.4）───────────────────────
// 原先本期增减各列恒显示 0、弹窗编辑按列名（两个「合计」同名）存、从不回显 ⇒ 改为与导出同一口径：
// 先取 source_accounts[列键]，年初 / 期末没有时退回年初 / 期末金额（report_excel_exporter._resolve_imp_value）
const pending = reactive(new Map<string, number | null>())
watch(() => props.rows, () => pending.clear())

function pendingKey(row: any, key: string): string {
  return `${row?.row_code ?? ''}|${key}`
}

function impVal(row: any, key: string): unknown {
  const k = pendingKey(row, key)
  if (pending.has(k)) return pending.get(k)
  const sa = row?.source_accounts
  const v = sa && typeof sa === 'object' && !Array.isArray(sa) ? sa[key] : undefined
  if (v != null && v !== '') return v
  if (key === 'opening_balance') return row?.prior_period_amount
  if (key === 'closing_balance') return row?.current_period_amount
  return null // 没填：显示「-」，编辑时输入框为空（不显示一个 0 让人在后面接着打）
}

/** 本组合计：本组各列都没填为 null */
function groupSum(row: any, cols: ImpColumn[]): number | null {
  const vals = cols.filter((c) => !c.sum).map((c) => impVal(row, c.key)).filter((v) => v != null && v !== '')
  return vals.length ? vals.reduce<number>((s, v) => s + (Number(v) || 0), 0) : null
}

/** 合计行不可改（年初 / 期末两列始终只读：按取数公式算） */
function canEdit(row: any): boolean {
  return !!props.editable && !!row?.row_code && !row.is_total_row
}

function onCommit(row: any, key: string, value: number | null): void {
  pending.set(pendingKey(row, key), value)
  emit('cell-edit', row, key, value)
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
