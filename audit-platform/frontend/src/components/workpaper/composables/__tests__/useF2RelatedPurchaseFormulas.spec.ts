import { describe, it, expect } from 'vitest'
import {
  defaultRelatedPurchaseSheet,
  enrichRelatedPurchaseItem,
  enrichRelatedPurchases,
  calcRelatedPurchaseTotals,
  migrateRelatedPurchaseSheet,
  emptyRelatedPurchaseItem,
  calcPriceVariance,
} from '../useF2RelatedPurchaseFormulas'

describe('useF2RelatedPurchaseFormulas', () => {
  it('default sheet has 10 rows', () => {
    expect(defaultRelatedPurchaseSheet().products).toHaveLength(10)
  })

  it('calculates ratios and unit price', () => {
    const row = {
      ...emptyRelatedPurchaseItem(),
      relatedQty: 100,
      relatedAmount: 10000,
      totalQty: 500,
      totalAmount: 60000,
      nonRelatedAvgPrice: 90,
    }
    const enriched = enrichRelatedPurchaseItem(row)
    expect(enriched.relatedUnitPrice).toBeCloseTo(100, 2)
    expect(enriched.currentQtyRatio).toBeCloseTo(0.2, 4)
    expect(enriched.currentAmtRatio).toBeCloseTo(10000 / 60000, 4)
    expect(enriched.priceVarianceRate).toBeCloseTo(calcPriceVariance(100, 90)!, 4)
    expect(enriched.isHighVariance).toBe(true)
  })

  it('column totals recalculate aggregate ratios', () => {
    const products = [
      {
        ...emptyRelatedPurchaseItem(),
        relatedQty: 100,
        relatedAmount: 10000,
        totalQty: 200,
        totalAmount: 25000,
      },
      {
        ...emptyRelatedPurchaseItem(),
        relatedQty: 50,
        relatedAmount: 4000,
        totalQty: 100,
        totalAmount: 12000,
      },
    ]
    const enriched = enrichRelatedPurchases(products)
    const totals = calcRelatedPurchaseTotals(enriched)
    expect(totals.relatedQty).toBe(150)
    expect(totals.relatedAmount).toBe(14000)
    expect(totals.currentQtyRatio).toBeCloseTo(150 / 300, 4)
    expect(totals.currentAmtRatio).toBeCloseTo(14000 / 37000, 4)
  })

  it('migrates legacy flat rows', () => {
    const legacy = [{
      rowId: 'old-1',
      relatedParty: '甲公司',
      itemName: '钢材',
      relatedPrice: 100,
      comparablePrice: 90,
      quantity: 50,
    }]
    const sheet = migrateRelatedPurchaseSheet(legacy)
    expect(sheet?.products[0].relatedPartyName).toBe('甲公司')
    expect(sheet?.products[0].relatedQty).toBe(50)
    expect(sheet?.products[0].relatedAmount).toBe(5000)
    expect(sheet?.products[0].nonRelatedAvgPrice).toBe(90)
  })
})
