/**
 * useWorkpaperWideTable — 宽表/多行表格统一滚动策略（D1/D3/D4 共用）
 */
import { computed, type Ref, type ComputedRef, type CSSProperties } from 'vue'

export const DEFAULT_ROW_THRESHOLD = 30
export const DEFAULT_WIDE_COLUMN_THRESHOLD = 12

export function useWorkpaperWideTable(options: {
  rowCount: Ref<number>
  columnCount?: Ref<number>
  rowThreshold?: number
  wideColumnThreshold?: number
  maxHeight?: number
}) {
  const rowThreshold = options.rowThreshold ?? DEFAULT_ROW_THRESHOLD
  const wideColumnThreshold = options.wideColumnThreshold ?? DEFAULT_WIDE_COLUMN_THRESHOLD
  const maxHeight = options.maxHeight ?? 560

  const useLargeTable: ComputedRef<boolean> = computed(
    () => options.rowCount.value > rowThreshold,
  )

  const isWideTable: ComputedRef<boolean> = computed(
    () => (options.columnCount?.value ?? 0) > wideColumnThreshold,
  )

  const tableMaxHeight: ComputedRef<number | undefined> = computed(() =>
    useLargeTable.value ? maxHeight : undefined,
  )

  const tableHeight: ComputedRef<number | string | undefined> = computed(() =>
    useLargeTable.value ? maxHeight : undefined,
  )

  const wrapperStyle: ComputedRef<CSSProperties | undefined> = computed(() =>
    isWideTable.value ? { overflowX: 'auto', width: '100%' } : undefined,
  )

  const minTableWidth: ComputedRef<string | undefined> = computed(() => {
    if (!isWideTable.value) return undefined
    const cols = options.columnCount?.value ?? 15
    return `${Math.max(cols * 96, 1200)}px`
  })

  return {
    useLargeTable,
    isWideTable,
    tableMaxHeight,
    tableHeight,
    wrapperStyle,
    minTableWidth,
  }
}

export default useWorkpaperWideTable
