/**
 * g5AgingScheme — 账龄切换迁移与解析
 */
import { describe, expect, it } from 'vitest'
import {
  remapAgingDataWithAggregation,
  remapDisclosureAgingRows,
  resolveG5AgingSegments,
  resolveG5DisplaySegments,
  validateCustomAgingLabels,
} from '../g5AgingScheme'

describe('resolveG5AgingSegments', () => {
  it('THREE_YEAR has 4 segments including over3', () => {
    const segs = resolveG5AgingSegments('THREE_YEAR')
    expect(segs.map((s) => s.key)).toEqual(['within1', 'y1to2', 'y2to3', 'over3'])
  })

  it('FIVE_YEAR has 6 segments', () => {
    const segs = resolveG5AgingSegments('FIVE_YEAR')
    expect(segs).toHaveLength(6)
    expect(segs.at(-1)?.key).toBe('over5')
  })

  it('CUSTOM uses stable custom-N keys', () => {
    const segs = resolveG5AgingSegments('CUSTOM', ['A', 'B', 'C'])
    expect(segs.map((s) => s.key)).toEqual(['custom-0', 'custom-1', 'custom-2'])
  })

  it('display segments overlay dual labels for FIVE_YEAR', () => {
    const segs = resolveG5DisplaySegments('FIVE_YEAR')
    expect(segs[0].label).toContain('/')
    expect(segs[0].key).toBe('within1')
  })
})

describe('remapAgingDataWithAggregation', () => {
  it('5→3 rolls y3to4+y4to5+over5 into over3', () => {
    const old = {
      within1: 10,
      y1to2: 20,
      y2to3: 30,
      y3to4: 40,
      y4to5: 50,
      over5: 60,
    }
    const next = remapAgingDataWithAggregation(old, resolveG5AgingSegments('THREE_YEAR'))
    expect(next).toEqual({
      within1: 10,
      y1to2: 20,
      y2to3: 30,
      over3: 150,
    })
  })

  it('3→5 rolls over3 into over5 without inventing middle bands', () => {
    const old = { within1: 1, y1to2: 2, y2to3: 3, over3: 90 }
    const next = remapAgingDataWithAggregation(old, resolveG5AgingSegments('FIVE_YEAR'))
    expect(next.within1).toBe(1)
    expect(next.y1to2).toBe(2)
    expect(next.y2to3).toBe(3)
    expect(next.y3to4).toBe(0)
    expect(next.y4to5).toBe(0)
    expect(next.over5).toBe(90)
  })

  it('preserves matching custom keys', () => {
    const segs = resolveG5AgingSegments('CUSTOM', ['短期', '长期'])
    const next = remapAgingDataWithAggregation({ 'custom-0': 5, 'custom-1': 7 }, segs)
    expect(next).toEqual({ 'custom-0': 5, 'custom-1': 7 })
  })
})

describe('remapDisclosureAgingRows', () => {
  it('aggregates provision and balance on 5→3', () => {
    const rows = [
      { id: '1', bandKey: 'within1', label: '1年以内', kind: 'band' as const, endBalance: 10, endProvision: 1, priorBalance: 8, priorProvision: 0.8 },
      { id: '2', bandKey: 'y1to2', label: '1-2年', kind: 'band' as const, endBalance: 20, endProvision: 2, priorBalance: 0, priorProvision: 0 },
      { id: '3', bandKey: 'y2to3', label: '2-3年', kind: 'band' as const, endBalance: 30, endProvision: 3, priorBalance: 0, priorProvision: 0 },
      { id: '4', bandKey: 'y3to4', label: '3-4年', kind: 'band' as const, endBalance: 40, endProvision: 4, priorBalance: 0, priorProvision: 0 },
      { id: '5', bandKey: 'y4to5', label: '4-5年', kind: 'band' as const, endBalance: 50, endProvision: 5, priorBalance: 0, priorProvision: 0 },
      { id: '6', bandKey: 'over5', label: '5年以上', kind: 'band' as const, endBalance: 60, endProvision: 6, priorBalance: 0, priorProvision: 0 },
      { id: 't', bandKey: 'total', label: '合计', kind: 'total' as const, endBalance: 210, endProvision: 21, priorBalance: 8, priorProvision: 0.8 },
    ]
    const next = remapDisclosureAgingRows(rows, resolveG5AgingSegments('THREE_YEAR'), (p) => p)
    const over3 = next.find((r) => r.bandKey === 'over3')
    const total = next.find((r) => r.kind === 'total')
    expect(over3?.endBalance).toBe(150)
    expect(over3?.endProvision).toBe(15)
    expect(total?.endBalance).toBe(210)
  })
})

describe('validateCustomAgingLabels', () => {
  it('rejects fewer than 2 or duplicates', () => {
    expect(validateCustomAgingLabels(['仅一段'])).toBeTruthy()
    expect(validateCustomAgingLabels(['A', 'A'])).toContain('重复')
    expect(validateCustomAgingLabels(['A', 'B'])).toBeNull()
  })
})
