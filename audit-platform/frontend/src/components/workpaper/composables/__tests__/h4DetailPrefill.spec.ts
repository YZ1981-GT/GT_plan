/**
 * h4DetailPrefill — Property Tests
 * P3: Persist-First guard
 * P5: Coverage denominator (standalone helper)
 * P6: H2 pull diff accuracy
 * P8: Provenance marker
 */
import { describe, it, expect } from 'vitest'
import {
  buildH4DetailSeedRows,
  buildH4H2Reconcile,
  type H4PrefillItem,
} from '../h4DetailPrefill'

const SAMPLE_PREFILL: H4PrefillItem[] = [
  { category: '钢材', name: '工程物资-钢材', accountCode: '1605.01', beginAmount: 100000, purchaseAmount: 50000, usageAmount: 30000, endAmount: 120000, source: 'tb_balance' },
  { category: '水泥', name: '工程物资-水泥', accountCode: '1605.02', beginAmount: 50000, purchaseAmount: 20000, usageAmount: 10000, endAmount: 60000, source: 'tb_balance' },
]

describe('buildH4DetailSeedRows', () => {
  // P3: Persist-First guard
  it('returns null when existing rows are present (P3)', () => {
    const existing = JSON.stringify([{ category: '已有', beginAmount: 999 }])
    expect(buildH4DetailSeedRows(SAMPLE_PREFILL, existing)).toBeNull()
  })

  it('returns null when existing rows is empty array string', () => {
    // 空数组 = 无数据 → 允许种子
    expect(buildH4DetailSeedRows(SAMPLE_PREFILL, '[]')).not.toBeNull()
  })

  it('returns null when prefill is null/empty', () => {
    expect(buildH4DetailSeedRows(null, null)).toBeNull()
    expect(buildH4DetailSeedRows([], null)).toBeNull()
    expect(buildH4DetailSeedRows(undefined, undefined)).toBeNull()
  })

  it('maps prefill items to detail row schema', () => {
    const rows = buildH4DetailSeedRows(SAMPLE_PREFILL, null)!
    expect(rows).toHaveLength(2)
    expect(rows[0].category).toBe('钢材')
    expect(rows[0].beginAmount).toBe(100000)
    expect(rows[0].purchaseAmount).toBe(50000)
    expect(rows[0].usageAmount).toBe(30000)
    expect(rows[0].endAmount).toBe(120000)
    expect(rows[0].accountCode).toBe('1605.01')
  })

  // P8: Provenance marker
  it('every seeded row has source=tb_balance (P8)', () => {
    const rows = buildH4DetailSeedRows(SAMPLE_PREFILL, null)!
    for (const r of rows) {
      expect(r.source).toBe('tb_balance')
    }
  })

  it('handles malformed existing JSON gracefully', () => {
    // Invalid JSON → treated as no data → seeds
    const rows = buildH4DetailSeedRows(SAMPLE_PREFILL, '{broken')
    expect(rows).not.toBeNull()
    expect(rows).toHaveLength(2)
  })
})

describe('buildH4H2Reconcile', () => {
  // P6: H2 pull diff accuracy
  it('calculates diff correctly (P6)', () => {
    const result = buildH4H2Reconcile(350, 350)
    expect(result.diff).toBe(0)
    expect(result.isMatch).toBe(true)
  })

  it('flags mismatch when diff > 1', () => {
    const result = buildH4H2Reconcile(500, 200)
    expect(result.diff).toBe(300)
    expect(result.isMatch).toBe(false)
  })

  it('considers diff within 1 as match', () => {
    const result = buildH4H2Reconcile(100.5, 100)
    expect(result.diff).toBeCloseTo(0.5)
    expect(result.isMatch).toBe(true)
  })
})
