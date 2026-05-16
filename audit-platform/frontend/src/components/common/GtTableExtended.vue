<template>
  <!--
    GtTableExtended — 列表展示型表格（R10 Spec B / Sprint 3.1.1）

    定位：
    - 所有"列表展示"场景的统一封装（只读为主）
    - 紫色表头 + 字号 class + 千分位 + 空状态 + 复制粘贴右键菜单
    - 内部基于 GtEditableTable，强制 editable=false，简化 props

    与 GtFormTable 的区别：
    - 本组件：只读列表（粘贴/撤销/dirty 标记不需要）
    - GtFormTable：行内编辑（含 dirty 标记 + 校验 + 撤销）

    复用现有所有 slot（toolbar-left/right/expand/col-*/footer-*/context-menu）。
  -->
  <GtEditableTable
    v-bind="$attrs"
    :model-value="modelValue"
    :columns="columns"
    :editable="false"
    :show-toolbar="showToolbar"
    :show-footer="showFooter"
    :show-summary="showSummary"
    :max-height="maxHeight"
    :default-sortable="defaultSortable"
    :group-by="groupBy"
    @ctx-formula="$emit('ctx-formula')"
    @ctx-compare="$emit('ctx-compare')"
    @row-click="(row, idx) => $emit('row-click', row, idx)"
    @cell-click="(row, col, idx) => $emit('cell-click', row, col, idx)"
    @selection-change="(rows) => $emit('selection-change', rows)"
  >
    <!-- 透传所有 slot -->
    <template v-for="(_, name) in $slots" #[name]="slotData">
      <slot :name="name" v-bind="slotData || {}" />
    </template>
  </GtEditableTable>
</template>

<script setup lang="ts">
/**
 * GtTableExtended (R10 Spec B / Sprint 3.1.1)
 *
 * 用法：
 * ```vue
 * <GtTableExtended :model-value="rows" :columns="cols" group-by="cycle">
 *   <template #toolbar-left>
 *     <el-button>...</el-button>
 *   </template>
 *   <template #col-amount="{ row }">
 *     <span class="gt-amt">{{ fmtAmount(row.amount) }}</span>
 *   </template>
 * </GtTableExtended>
 * ```
 *
 * 决策树（COMPONENT_USAGE_GUIDE.md）：
 * - 需要行内编辑 / dirty / 撤销？ → GtFormTable
 * - 仅展示 + 排序 + 筛选 + 复制粘贴？ → GtTableExtended（本组件）
 * - 兼容已有代码？ → GtEditableTable wrapper（60 天观察期，逐步迁移）
 */
import GtEditableTable, { type GtColumn } from './GtEditableTable.vue'

defineProps<{
  modelValue: Record<string, any>[]
  columns: GtColumn[]
  showToolbar?: boolean
  showFooter?: boolean
  showSummary?: boolean
  maxHeight?: string | number
  defaultSortable?: boolean
  groupBy?: string
  summaryMethod?: (param: { columns: any[]; data: any[] }) => any[]
}>()

defineEmits<{
  (e: 'ctx-formula'): void
  (e: 'ctx-compare'): void
  (e: 'row-click', row: any, index: number): void
  (e: 'cell-click', row: any, col: GtColumn, index: number): void
  (e: 'selection-change', rows: any[]): void
}>()

export type { GtColumn } from './GtEditableTable.vue'
</script>
