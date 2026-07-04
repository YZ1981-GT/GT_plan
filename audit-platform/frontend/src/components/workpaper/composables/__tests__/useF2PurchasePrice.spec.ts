import { describe, it, expect } from 'vitest'
import {
  enrichPurchasePriceRow,
  type PurchasePriceRow,
} from '../useF2PurchasePrice'

function rowWithMonths(
  months: Array<{ amount: number; qty: number }>,
  priorAvgPrice = 0,
): PurchasePriceRow {
  const padded = Array.from({ length: 12 }, (_, i) => months[i] ?? { amount: 0, qty: 0 })
  return {
    id: '1',
    materialName: '钢材',
    spec: 'A',
    unit: '吨',
    months: padded,
    priorAvgPrice,
  }
}

describe('useF2PurchasePrice enrichPurchasePriceRow', () => {
  it('annualAvgPrice = totalAmount / totalQty', () => {
    const row = rowWithMonths([
      { amount: 1000, qty: 10 },
      { amount: 500, qty: 5 },
    ])
    const enriched = enrichPurchasePriceRow(row)
    expect(enriched.annualTotalAmount).toBe(1500)
    expect(enriched.annualTotalQty).toBe(15)
    expect(enriched.annualAvgPrice).toBe(100)
  })

  it('flags month unit price deviating >30% from annual average', () => {
    const row = rowWithMonths([
      { amount: 1000, qty: 10 }, // 100
      { amount: 200, qty: 1 },   // 200 → +100%
    ])
    const enriched = enrichPurchasePriceRow(row)
    expect(enriched.enrichedMonths[1].priceAbnormal).toBe(true)
    expect(enriched.enrichedMonths[0].priceAbnormal).toBe(false)
  })

  it('changeRate vs priorAvgPrice and isAbnormal when |rate| > 30', () => {
    const row = rowWithMonths([{ amount: 1300, qty: 10 }], 100)
    const enriched = enrichPurchasePriceRow(row)
    expect(enriched.annualAvgPrice).toBe(130)
    expect(enriched.changeRate).toBeCloseTo(30, 1)
    expect(enriched.isAbnormal).toBe(false)

    const row2 = rowWithMonths([{ amount: 1400, qty: 10 }], 100)
    expect(enrichPurchasePriceRow(row2).isAbnormal).toBe(true)
  })
})
