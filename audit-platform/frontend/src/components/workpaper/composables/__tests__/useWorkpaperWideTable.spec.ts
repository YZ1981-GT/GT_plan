import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useWorkpaperWideTable,
  DEFAULT_ROW_THRESHOLD,
  DEFAULT_WIDE_COLUMN_THRESHOLD,
} from '../useWorkpaperWideTable'

describe('useWorkpaperWideTable', () => {
  it('enables large table scroll when row count exceeds threshold', () => {
    const rowCount = ref(DEFAULT_ROW_THRESHOLD + 1)
    const { useLargeTable, tableMaxHeight } = useWorkpaperWideTable({ rowCount })
    expect(useLargeTable.value).toBe(true)
    expect(tableMaxHeight.value).toBe(560)
  })

  it('does not cap height when row count is at or below threshold', () => {
    const rowCount = ref(DEFAULT_ROW_THRESHOLD)
    const { useLargeTable, tableMaxHeight } = useWorkpaperWideTable({ rowCount })
    expect(useLargeTable.value).toBe(false)
    expect(tableMaxHeight.value).toBeUndefined()
  })

  it('enables horizontal wrapper when column count exceeds wide threshold', () => {
    const rowCount = ref(5)
    const columnCount = ref(DEFAULT_WIDE_COLUMN_THRESHOLD + 1)
    const { isWideTable, wrapperStyle, minTableWidth } = useWorkpaperWideTable({
      rowCount,
      columnCount,
    })
    expect(isWideTable.value).toBe(true)
    expect(wrapperStyle.value).toEqual({ overflowX: 'auto', width: '100%' })
    expect(minTableWidth.value).toBe(`${(DEFAULT_WIDE_COLUMN_THRESHOLD + 1) * 96}px`)
  })

  it('skips horizontal wrapper when column count is at wide threshold', () => {
    const rowCount = ref(5)
    const columnCount = ref(DEFAULT_WIDE_COLUMN_THRESHOLD)
    const { isWideTable, wrapperStyle, minTableWidth } = useWorkpaperWideTable({
      rowCount,
      columnCount,
    })
    expect(isWideTable.value).toBe(false)
    expect(wrapperStyle.value).toBeUndefined()
    expect(minTableWidth.value).toBeUndefined()
  })
})
