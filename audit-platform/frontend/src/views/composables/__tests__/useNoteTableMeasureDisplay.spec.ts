import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'

vi.mock('@/services/displayPreferencesApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/displayPreferencesApi')>()),
  getDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
  patchDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
}))

import { useNoteTableMeasureDisplay } from '../useNoteTableMeasureDisplay'

describe('useNoteTableMeasureDisplay', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('matched table 按稳定 column_id 开放固定列，并给 ratio 正确尺度', () => {
    const table = ref<any>({
      table_id: 't1', measure_status: 'matched', headers: ['项目', '金额', '比例'],
      column_ids: ['label-id', 'amount-id', 'ratio-id'],
      column_kinds: ['text', 'amount', 'ratio'],
      column_ratio_scales: [null, null, 'fraction'],
    })
    const tableRef = ref<any>({ doLayout: vi.fn() })
    const display = useNoteTableMeasureDisplay(table, tableRef)
    expect(display.fixedPageKey.value).toBe('disclosure-editor:t1')
    expect(display.fixedColumns.value.map((col) => col.key)).toEqual(['label', 'amount-id', 'ratio-id'])
    expect(display.measureKind(2)).toBe('ratio')
    expect(display.ratioScale(2)).toBe('fraction')
    expect(display.fixedFor(0)).toBe('left')
  })

  it('unmatched/invalid 表不猜 kind、不开放固定列', () => {
    const table = ref<any>({
      table_id: 't1', measure_status: 'invalid', headers: ['项目', '金额'],
      column_ids: ['label-id', 'amount-id'], column_kinds: ['text', 'amount'], column_ratio_scales: [null, null],
    })
    const display = useNoteTableMeasureDisplay(table, ref<any>(null))
    expect(display.fixedPageKey.value).toBe('')
    expect(display.measureKind(1)).toBeNull()
    expect(display.fixedFor(0)).toBe(false)
  })

  it('未对齐数组不虚构 column key，固定列按钮不会保存错表', () => {
    const table = ref<any>({ table_id: 't1', measure_status: 'matched', headers: ['项目', '金额'], column_ids: ['label-id'] })
    const display = useNoteTableMeasureDisplay(table, ref<any>(null))
    expect(display.columnKey(1)).toBe('')
    expect(display.fixedColumns.value).toEqual([])
  })
})
