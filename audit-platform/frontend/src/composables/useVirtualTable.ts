/**
 * useVirtualTable - 条件虚拟化 composable
 *
 * 当数据行数 > 500 时自动切换到 el-table-v2 虚拟滚动模式，
 * ≤500 行时使用普通 el-table 保持现有交互。
 *
 * 复用 LedgerPenetration 已有的 el-table-v2 模式：
 * headerCellRenderer / cellRenderer / rowEventHandlers
 */
import { computed, ref, h, type Ref, type ComputedRef } from 'vue'

/** 虚拟化阈值：超过此行数启用 el-table-v2 */
export const VIRTUAL_THRESHOLD = 500

/** 列定义 */
export interface VirtualColumn {
  key: string
  dataKey: string
  title: string
  width: number
  align?: 'left' | 'center' | 'right'
  sortable?: boolean
  flexGrow?: number
  /** 自定义单元格渲染 */
  cellRenderer?: (params: { cellData: any; rowData: any; rowIndex: number }) => any
  /** 自定义表头渲染 */
  headerCellRenderer?: (params: { column: any }) => any
}

/** useVirtualTable 参数 */
export interface UseVirtualTableOptions {
  /** 数据行数组 */
  rows: Ref<any[]> | ComputedRef<any[]>
  /** 列配置 */
  columns: Ref<VirtualColumn[]> | ComputedRef<VirtualColumn[]>
  /** 表格宽度（px） */
  width?: Ref<number> | number
  /** 表格高度（px） */
  height?: Ref<number> | number
  /** 行高（px） */
  rowHeight?: number
  /** 表头高度（px） */
  headerHeight?: number
  /** 行双击回调 */
  onRowDblclick?: (row: any) => void
  /** 行右键回调 */
  onRowContextmenu?: (row: any, event: Event) => void
  /** 行点击回调 */
  onRowClick?: (row: any) => void
}

export function useVirtualTable(options: UseVirtualTableOptions) {
  const {
    rows,
    columns,
    rowHeight = 36,
    headerHeight = 40,
    onRowDblclick,
    onRowContextmenu,
    onRowClick,
  } = options

  const width = typeof options.width === 'number'
    ? ref(options.width)
    : options.width ?? ref(1200)

  const height = typeof options.height === 'number'
    ? ref(options.height)
    : options.height ?? ref(600)

  /** 是否启用虚拟滚动 */
  const useVirtual = computed(() => rows.value.length > VIRTUAL_THRESHOLD)

  /** el-table-v2 的 props */
  const tableProps = computed(() => ({
    columns: columns.value,
    data: rows.value,
    width: typeof width === 'number' ? width : width.value,
    height: typeof height === 'number' ? height : height.value,
    rowHeight,
    headerHeight,
    fixed: true,
  }))

  /** 默认 headerCellRenderer：带列标题 + 对齐 */
  function headerCellRenderer({ column }: { column: any }) {
    const align = column.align || 'left'
    return h(
      'div',
      {
        class: 'gt-vcol-header',
        style: { textAlign: align, width: '100%', padding: '0 8px' },
      },
      [h('span', { class: 'gt-vcol-title' }, column.title)],
    )
  }

  /** 默认 cellRenderer：文本渲染 */
  function cellRenderer({ cellData }: { cellData: any }) {
    if (cellData == null) return h('span', { class: 'gt-vcell-empty' }, '-')
    return h('span', {}, String(cellData))
  }

  /** 行事件 handlers（右键 + 双击 + 单击） */
  const rowEventHandlers = computed(() => ({
    onContextmenu: ({ rowData, event }: { rowData: any; event: Event }) => {
      if (onRowContextmenu) onRowContextmenu(rowData, event)
    },
    onDblclick: ({ rowData }: { rowData: any }) => {
      if (onRowDblclick) onRowDblclick(rowData)
    },
    onClick: ({ rowData }: { rowData: any }) => {
      if (onRowClick) onRowClick(rowData)
    },
  }))

  return {
    useVirtual,
    tableProps,
    headerCellRenderer,
    cellRenderer,
    rowEventHandlers,
    /** 暴露阈值常量供外部使用 */
    VIRTUAL_THRESHOLD,
  }
}
