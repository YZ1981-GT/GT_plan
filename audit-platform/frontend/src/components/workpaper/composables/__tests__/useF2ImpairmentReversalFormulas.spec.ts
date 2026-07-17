import { describe, it, expect } from 'vitest'
import {
  defaultReversalSheet,
  enrichReversalItem,
  enrichReversalItems,
  calcReversalTotals,
  calcReversalTotal,
  calcEffectiveAccountSplit,
  migrateReversalSheet,
  emptyReversalItem,
} from '../useF2ImpairmentReversalFormulas'

describe('useF2ImpairmentReversalFormulas', () => {
  it('default sheet has 10 rows', () => {
    expect(defaultReversalSheet().products).toHaveLength(10)
  })

  it('calculates reversal proportional to issuance', () => {
    const row = {
      ...emptyReversalItem(),
      openingQty: 100,
      priorProvision: 1000,
      issuance: { total: 40, production: 20, sales: 20, rnd: 0, other: 0 },
    }
    expect(calcReversalTotal(row)).toBeCloseTo(400, 2)
    const enriched = enrichReversalItem(row)
    expect(enriched.reversalTotal).toBeCloseTo(400, 2)
    expect(enriched.effectiveCostOfSales).toBeCloseTo(400, 2)
    expect(enriched.verifyOk).toBe(true)
  })

  it('allocates reversal across accounts by issuance mix', () => {
    const row = {
      ...emptyReversalItem(),
      openingQty: 100,
      priorProvision: 500,
      issuance: { total: 50, production: 10, sales: 20, rnd: 15, other: 5 },
    }
    const reversal = calcReversalTotal(row)
    expect(reversal).toBeCloseTo(250, 2)
    const split = calcEffectiveAccountSplit(row, reversal)
    expect(split.costOfSales).toBeCloseTo(150, 2)
    expect(split.rndExpense).toBeCloseTo(75, 2)
    expect(split.other).toBeCloseTo(25, 2)
  })

  it('skips reversal when separate provision is false', () => {
    const row = {
      ...emptyReversalItem(),
      separateProvision: false,
      openingQty: 100,
      priorProvision: 1000,
      issuance: { total: 50, production: 50, sales: 0, rnd: 0, other: 0 },
    }
    expect(calcReversalTotal(row)).toBe(0)
  })

  it('flags issuance breakdown mismatch', () => {
    const row = {
      ...emptyReversalItem(),
      openingQty: 100,
      issuance: { total: 50, production: 10, sales: 10, rnd: 10, other: 10 },
    }
    expect(enrichReversalItem(row).issuanceMismatch).toBe(true)
  })

  it('column totals aggregate correctly', () => {
    const products = [
      {
        ...emptyReversalItem(),
        openingQty: 100,
        openingUnitPrice: 10,
        priorProvision: 200,
        issuance: { total: 50, production: 50, sales: 0, rnd: 0, other: 0 },
      },
      {
        ...emptyReversalItem(),
        openingQty: 50,
        openingUnitPrice: 20,
        priorProvision: 100,
        issuance: { total: 25, production: 0, sales: 25, rnd: 0, other: 0 },
      },
    ]
    const enriched = enrichReversalItems(products)
    const totals = calcReversalTotals(enriched)
    expect(totals.openingAmount).toBeCloseTo(2000, 2)
    expect(totals.reversalTotal).toBeCloseTo(150, 2)
  })

  it('migrates legacy flat rows', () => {
    const legacy = [{
      rowId: 'old-1',
      itemName: '产成品A',
      bookCost: 5000,
      priorProvision: 500,
      reversalAmount: 200,
    }]
    const sheet = migrateReversalSheet(legacy)
    expect(sheet?.products[0].itemName).toBe('产成品A')
    expect(sheet?.products[0].priorProvision).toBe(500)
    expect(sheet?.products[0].accountSplit.costOfSales).toBe(200)
  })
})
