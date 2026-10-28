/**
 * useWorkpaperBrowseMode — 宽表浏览模式（>threshold 行时 el-table-v2 速览，双击切编辑）
 * 参照 D2TabDetail browseMode 模式。
 *
 * 默认阈值随表格编辑方式（spec excel-style-table-editing 4.3，真浏览器实测 10 列可编辑表的挂载耗时）：
 * - 经典方式：每格常驻输入框，30 行约 135 ms、100 行约 505 ms ⇒ 超过 30 行走速览；
 * - Excel / 单击编辑：平时只渲染文本，100 行约 175 ms、200 行约 344 ms ⇒ 100 行以内直接用可编辑表格。
 * 页面显式传 threshold 时以页面为准。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useVirtualTable, type VirtualColumn } from '@/composables/useVirtualTable'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

/** 经典方式（单元格输入框常驻）的速览阈值 */
export const BROWSE_MODE_ROW_THRESHOLD = 30
/** Excel / 单击编辑方式（平时只显示文本）的速览阈值 */
export const BROWSE_MODE_ROW_THRESHOLD_TEXT = 100

export function useWorkpaperBrowseMode(options: {
  rows: Ref<unknown[]> | ComputedRef<unknown[]>
  virtualColumns: Ref<VirtualColumn[]> | ComputedRef<VirtualColumn[]>
  threshold?: number
  tableWidth?: number
  tableHeight?: number
}) {
  let prefs: ReturnType<typeof useDisplayPrefsStore> | null = null
  try { prefs = useDisplayPrefsStore() } catch { prefs = null }
  const threshold = computed(() => options.threshold
    ?? ((prefs?.gridEditMode ?? 'excel') === 'classic' ? BROWSE_MODE_ROW_THRESHOLD : BROWSE_MODE_ROW_THRESHOLD_TEXT))
  const browseMode = ref(true)
  const tableWidth = ref(options.tableWidth ?? 1200)
  const tableHeight = options.tableHeight ?? 560

  const useVirtualScroll = computed(() => options.rows.value.length > threshold.value)

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
