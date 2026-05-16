<template>
  <!--
    GtFormTable — 行内编辑型表格（R10 Spec B / Sprint 3.1.2）

    定位：
    - 所有"行内编辑 + dirty 标记 + 校验 + 撤销"场景的统一封装
    - 内部基于 GtEditableTable，强制 editable=true，简化 props

    与 GtTableExtended 的区别：
    - 本组件：行内编辑（dirty 标记 / 撤销栈 / 校验）
    - GtTableExtended：只读列表

    使用方：Adjustments / InternalTradeSheet / InternalCashFlowSheet 等需要批量编辑的场景。
  -->
  <GtEditableTable
    v-bind="$attrs"
    :model-value="modelValue"
    :columns="columns"
    :editable="true"
    :show-selection="showSelection"
    :lazy-edit="lazyEdit"
    :show-toolbar="showToolbar"
    :show-footer="showFooter"
    :show-summary="showSummary"
    :max-height="maxHeight"
    :default-sortable="defaultSortable"
    :group-by="groupBy"
    @update:model-value="(v: any[]) => $emit('update:modelValue', v)"
    @save="$emit('save')"
    @ctx-formula="$emit('ctx-formula')"
    @ctx-compare="$emit('ctx-compare')"
    @row-click="(row, idx) => $emit('row-click', row, idx)"
    @cell-click="(row, col, idx) => $emit('cell-click', row, col, idx)"
    @selection-change="(rows) => $emit('selection-change', rows)"
    @edit-change="(v) => $emit('edit-change', v)"
    @dirty-change="(v) => $emit('dirty-change', v)"
  >
    <template v-for="(_, name) in $slots" #[name]="slotData">
      <slot :name="name" v-bind="slotData || {}" />
    </template>
  </GtEditableTable>
</template>

<script setup lang="ts">
/**
 * GtFormTable (R10 Spec B / Sprint 3.1.2)
 *
 * 用法：
 * ```vue
 * <GtFormTable
 *   v-model="entries"
 *   :columns="adjColumns"
 *   show-selection
 *   @save="onSave"
 *   @dirty-change="onDirtyChange"
 * />
 * ```
 *
 * 决策树（COMPONENT_USAGE_GUIDE.md）：
 * - 需要行内编辑 / dirty / 撤销？ → GtFormTable（本组件）
 * - 仅展示 + 排序 + 筛选 + 复制粘贴？ → GtTableExtended
 * - 兼容已有代码？ → GtEditableTable wrapper（60 天观察期，逐步迁移）
 */
import GtEditableTable, { type GtColumn } from './GtEditableTable.vue'

defineProps<{
  modelValue: Record<string, any>[]
  columns: GtColumn[]
  showSelection?: boolean
  lazyEdit?: boolean
  showToolbar?: boolean
  showFooter?: boolean
  showSummary?: boolean
  maxHeight?: string | number
  defaultSortable?: boolean
  groupBy?: string
  summaryMethod?: (param: { columns: any[]; data: any[] }) => any[]
  defaultRow?: () => Record<string, any>
}>()

defineEmits<{
  (e: 'update:modelValue', data: Record<string, any>[]): void
  (e: 'save'): void
  (e: 'ctx-formula'): void
  (e: 'ctx-compare'): void
  (e: 'row-click', row: any, index: number): void
  (e: 'cell-click', row: any, col: GtColumn, index: number): void
  (e: 'selection-change', rows: any[]): void
  (e: 'edit-change', isEditing: boolean): void
  (e: 'dirty-change', isDirty: boolean): void
}>()

export type { GtColumn } from './GtEditableTable.vue'
</script>
