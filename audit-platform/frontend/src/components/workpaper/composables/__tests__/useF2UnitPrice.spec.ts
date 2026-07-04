import { describe, it, expect } from 'vitest'
import { enrichUnitPriceRow, type UnitPriceRow } from '../useF2UnitPrice'

function row(overrides: Partial<UnitPriceRow> = {}): UnitPriceRow {
  return {
    id: '1',
    materialName: '铜材',
    spec: 'A',
    unit: '吨',
    priceT: 0, priceT1: 0, priceT2: 0,
    qtyT: 0, qtyT1: 0, qtyT2: 0,
    industryAvgPrice: 0,
    analysisConclusion: '', remark: '',
    ...overrides,
  }
}

describe('useF2UnitPrice enrichUnitPriceRow', () => {
  it('amount = price × qty for each period', () => {
    const enriched = enrichUnitPriceRow(row({
      priceT: 100, qtyT: 10,
      priceT1: 90, qtyT1: 8,
      priceT2: 80, qtyT2: 5,
    }))
    expect(enriched.amountT).toBe(1000)
    expect(enriched.amountT1).toBe(720)
    expect(enriched.amountT2).toBe(400)
  })

  it('yoyChangeRate = (T - T-1) / T-1', () => {
    const enriched = enrichUnitPriceRow(row({ priceT: 120, priceT1: 100 }))
    expect(enriched.yoyChangeRate).toBeCloseTo(0.2, 5)
  })

  it('deviationPct and isHighDeviation when |deviation| > 20%', () => {
    const ok = enrichUnitPriceRow(row({ priceT: 110, industryAvgPrice: 100 }))
    expect(ok.deviationPct).toBeCloseTo(10, 1)
    expect(ok.isHighDeviation).toBe(false)

    const bad = enrichUnitPriceRow(row({ priceT: 130, industryAvgPrice: 100 }))
    expect(bad.deviationPct).toBeCloseTo(30, 1)
    expect(bad.isHighDeviation).toBe(true)
    expect(bad.highlight).toBe(true)
  })
})
