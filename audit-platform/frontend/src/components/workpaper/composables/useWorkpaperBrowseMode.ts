/**
 * useWorkpaperBrowseMode — 宽表浏览模式（>threshold 行时 el-table-v2 速览，双击切编辑）
 * 参照 D2TabDetail browseMode 模式，阈值默认 30 行。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useVirtualTable, type VirtualColumn } from '@/composables/useVirtualTable'

export const BROWSE_MODE_ROW_THRESHOLD = 30

export function useWorkpaperBrowseMode(options: {
  rows: Ref<unknown[]> | ComputedRef<unknown[]>
  virtualColumns: Ref<VirtualColumn[]> | ComputedRef<VirtualColumn[]>
  threshold?: number
  tableWidth?: number
  tableHeight?: number
}) {
  const threshold = options.threshold ?? BROWSE_MODE_ROW_THRESHOLD
  const browseMode = ref(true)
  const tableWidth = ref(options.tableWidth ?? 1200)
  const tableHeight = options.tableHeight ?? 560

  const useVirtualScroll = computed(() => options.rows.value.length > threshold)

  const { rowEventHandlers } = useVirtualTable({
    rows: options.rows,
    columns: options.virtualColumns,
    width: tableWidth,
    height: tableHeight,
    onRowDblclick: () => { browseMode.value = false },
  })

  function toggleBrowseMode(): void {
    browseMode.value = !browseMode.value
  }

  return {
    browseMode,
    useVirtualScroll,
    rowEventHandlers,
    tableWidth,
    tableHeight,
    toggleBrowseMode,
  }
}

export default useWorkpaperBrowseMode
