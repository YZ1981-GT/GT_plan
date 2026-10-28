import { describe, it, expect } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  BROWSE_MODE_ROW_THRESHOLD, BROWSE_MODE_ROW_THRESHOLD_TEXT, useWorkpaperBrowseMode,
} from '../useWorkpaperBrowseMode'
import { virtualTextCol } from '../virtualColumnHelpers'

const rowsOf = (n: number) => ref(Array.from({ length: n }, (_, i) => ({ id: i })))
const virtualColumns = computed(() => [virtualTextCol('id', 'ID', 60)])

describe('useWorkpaperBrowseMode', () => {
  it('阈值：经典方式 30 行、Excel / 单击编辑方式 100 行（spec excel-style-table-editing 4.3）', () => {
    expect(BROWSE_MODE_ROW_THRESHOLD).toBe(30)
    expect(BROWSE_MODE_ROW_THRESHOLD_TEXT).toBe(100)
  })

  it('经典方式：≤30 行不启用虚拟速览，>30 行启用', () => {
    useDisplayPrefsStore().gridEditMode = 'classic'
    expect(useWorkpaperBrowseMode({ rows: rowsOf(20), virtualColumns }).useVirtualScroll.value).toBe(false)
    const { useVirtualScroll, browseMode } = useWorkpaperBrowseMode({ rows: rowsOf(35), virtualColumns })
    expect(useVirtualScroll.value).toBe(true)
    expect(browseMode.value).toBe(true)
  })

  it('Excel 方式（默认）：100 行以内直接用可编辑表格，超过才走速览', () => {
    expect(useDisplayPrefsStore().gridEditMode).toBe('excel')
    expect(useWorkpaperBrowseMode({ rows: rowsOf(35), virtualColumns }).useVirtualScroll.value).toBe(false)
    expect(useWorkpaperBrowseMode({ rows: rowsOf(100), virtualColumns }).useVirtualScroll.value).toBe(false)
    expect(useWorkpaperBrowseMode({ rows: rowsOf(101), virtualColumns }).useVirtualScroll.value).toBe(true)
  })

  it('切换编辑方式即时生效；页面显式传 threshold 时以页面为准', async () => {
    const prefs = useDisplayPrefsStore()
    const { useVirtualScroll } = useWorkpaperBrowseMode({ rows: rowsOf(50), virtualColumns })
    expect(useVirtualScroll.value).toBe(false)
    prefs.gridEditMode = 'classic'
    await nextTick()
    expect(useVirtualScroll.value).toBe(true)
    prefs.gridEditMode = 'click'
    await nextTick()
    expect(useVirtualScroll.value).toBe(false)
    expect(useWorkpaperBrowseMode({ rows: rowsOf(50), virtualColumns, threshold: 10 }).useVirtualScroll.value).toBe(true)
  })
})
