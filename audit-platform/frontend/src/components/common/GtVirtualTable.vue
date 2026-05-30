<template>
  <div class="gt-virtual-table-wrapper">
    <!-- 虚拟滚动模式：数据行 > 500 -->
    <el-table-v2
      v-if="useVirtual"
      :columns="virtualColumns"
      :data="data"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="rowHeight"
      :header-height="headerHeight"
      :row-event-handlers="rowEventHandlers"
      :row-class="virtualRowClass"
      fixed
    />
    <!-- 标准模式：数据行 ≤ 500，使用 el-table -->
    <el-table
      v-else
      :data="data"
      :border="border"
      :max-height="tableHeight"
      :highlight-current-row="highlightCurrentRow"
      :row-class-name="rowClassName"
      size="small"
      style="width: 100%"
      @row-click="$emit('row-click', $event)"
      @row-dblclick="$emit('row-dblclick', $event)"
      @row-contextmenu="onElTableContextmenu"
      @selection-change="$emit('selection-change', $event)"
    >
      <slot />
    </el-table>
    <!-- 底部虚拟滚动提示 -->
    <div v-if="useVirtual" class="gt-vt-status-bar">
      <span>共 {{ data.length.toLocaleString() }} 行</span>
      <span class="gt-vt-badge">虚拟滚动已启用</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref, toRef } from 'vue'
import { useVirtualTable, VIRTUAL_THRESHOLD, type VirtualColumn } from '@/composables/useVirtualTable'

export interface GtVirtualTableColumn {
  key: string
  prop: string
  label: string
  width?: number
  minWidth?: number
  align?: 'left' | 'center' | 'right'
  sortable?: boolean
  formatter?: (row: any, col: any, cellValue: any) => string
}

const props = withDefaults(defineProps<{
  data: any[]
  columns?: GtVirtualTableColumn[]
  border?: boolean
  highlightCurrentRow?: boolean
  rowClassName?: string | ((params: { row: any; rowIndex: number }) => string)
  width?: number
  height?: number
  rowHeight?: number
  headerHeight?: number
}>(), {
  columns: () => [],
  border: true,
  highlightCurrentRow: true,
  width: 1200,
  height: 600,
  rowHeight: 36,
  headerHeight: 40,
})

const emit = defineEmits<{
  (e: 'row-click', row: any): void
  (e: 'row-dblclick', row: any): void
  (e: 'row-contextmenu', row: any, column: any, event: MouseEvent): void
  (e: 'selection-change', rows: any[]): void
}>()

const tableWidth = ref(props.width)
const tableHeight = ref(props.height)

/** 将 GtVirtualTableColumn 转为 el-table-v2 的 VirtualColumn */
const virtualColumns = computed<VirtualColumn[]>(() =>
  props.columns.map((col) => ({
    key: col.key || col.prop,
    dataKey: col.prop,
    title: col.label,
    width: col.width || col.minWidth || 150,
    align: col.align || 'left',
    sortable: col.sortable ?? false,
    cellRenderer: col.formatter
      ? ({ rowData, cellData }: any) => h('span', {}, col.formatter!(rowData, col, cellData))
      : undefined,
    headerCellRenderer: ({ column }: any) =>
      h('div', {
        class: 'gt-vcol-header',
        style: { textAlign: col.align || 'left', width: '100%', padding: '0 8px' },
      }, [h('span', { class: 'gt-vcol-title' }, col.label)]),
  })),
)

const { useVirtual, rowEventHandlers } = useVirtualTable({
  rows: toRef(props, 'data'),
  columns: virtualColumns,
  width: tableWidth,
  height: tableHeight,
  rowHeight: props.rowHeight,
  headerHeight: props.headerHeight,
  onRowDblclick: (row) => emit('row-dblclick', row),
  onRowContextmenu: (row, event) => emit('row-contextmenu', row, null, event as MouseEvent),
  onRowClick: (row) => emit('row-click', row),
})

/** 虚拟模式行样式 */
function virtualRowClass({ rowIndex }: { rowIndex: number }) {
  return rowIndex % 2 === 1 ? 'gt-vrow-stripe' : ''
}

/** el-table 右键菜单事件转发 */
function onElTableContextmenu(row: any, column: any, event: MouseEvent) {
  emit('row-contextmenu', row, column, event)
}
</script>

<style scoped>
.gt-virtual-table-wrapper {
  width: 100%;
}

.gt-vt-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
}

.gt-vt-badge {
  color: var(--el-color-success);
  font-weight: 500;
}

.gt-vcol-header {
  display: flex;
  align-items: center;
  height: 100%;
}

.gt-vcol-title {
  font-weight: 600;
  font-size: 13px;
}

:deep(.gt-vrow-stripe) {
  background: var(--el-fill-color-lighter);
}
</style>
