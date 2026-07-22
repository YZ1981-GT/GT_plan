import { describe, expect, it } from 'vitest'
import {
  labeledRowSources,
  showRowSourceDetail,
  uniqueRowSources,
} from '../g7DisclosureTableMeta'

describe('g7DisclosureTableMeta', () => {
  it('dedupes unique row sources', () => {
    const rows = [
      { id: 'a', label: '甲', values: {}, kind: 'data' as const, source: 'G7-4' },
      { id: 'b', label: '乙', values: {}, kind: 'data' as const, source: 'G7-4' },
      { id: 'c', label: '丙', values: {}, kind: 'data' as const, source: 'G7-5' },
    ]
    expect(uniqueRowSources(rows)).toEqual(['G7-4', 'G7-5'])
  })

  it('shows row detail when sources differ or many rows share one source', () => {
    const few = [
      { id: 'a', label: '甲', values: {}, kind: 'data' as const, source: 'G7-4' },
      { id: 'b', label: '乙', values: {}, kind: 'data' as const, source: 'G7-4' },
    ]
    expect(showRowSourceDetail(few)).toBe(false)

    const many = Array.from({ length: 4 }, (_, i) => ({
      id: `r${i}`,
      label: `单位${i}`,
      values: {},
      kind: 'data' as const,
      source: 'G7-4',
    }))
    expect(showRowSourceDetail(many)).toBe(true)

    const mixed = [
      { id: 'a', label: '甲', values: {}, kind: 'data' as const, source: 'G7-4' },
      { id: 'b', label: '乙', values: {}, kind: 'data' as const, source: 'G7-5' },
    ]
    expect(showRowSourceDetail(mixed)).toBe(true)
    expect(labeledRowSources(mixed)).toHaveLength(2)
  })
})
