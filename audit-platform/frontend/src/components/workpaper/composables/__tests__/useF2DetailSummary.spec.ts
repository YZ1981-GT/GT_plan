import { describe, it, expect } from 'vitest'
import { calcSubtotal, calcUnitPrice } from '../useF2InvMaiFormulaEngine'

describe('useF2DetailSummary aggregation', () => {
  it('fmtPrice via calcUnitPrice: qty=0 returns empty', () => {
    expect(calcUnitPrice(100, 0)).toBe('')
  })

  it('aging total = sum of 4 segments', () => {
    const segments = [100, 200, 50, 30]
    expect(calcSubtotal(segments)).toBe(380)
  })

  it('unit price = amount / qty', () => {
    expect(calcUnitPrice(1000, 100)).toBe(10)
  })
})
