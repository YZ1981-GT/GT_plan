import { describe, it, expect } from 'vitest'
import {
  defaultImpairmentSheet,
  enrichImpairmentProduct,
  enrichImpairmentProducts,
  calcImpairmentTotals,
  calcCategorySummaries,
  migrateImpairmentSheet,
  effectiveUnitPrice,
  emptyImpairmentProduct,
  isBlankProduct,
  pruneBlankProducts,
} from '../useF2ImpairmentTestFormulas'

describe('useF2ImpairmentTestFormulas', () => {
  it('default sheet has 1 sample row (no reserved blanks)', () => {
    expect(defaultImpairmentSheet().products).toHaveLength(1)
    expect(isBlankProduct(defaultImpairmentSheet().products[0])).toBe(true)
  })

  it('uses contract price over market price', () => {
    const row = {
      ...emptyImpairmentProduct(),
      pricePreContract: 100,
      priceContract: 80,
    }
    expect(effectiveUnitPrice(row)).toBe(80)
  })

  it('calculates NRV and required provision', () => {
    const row = {
      ...emptyImpairmentProduct(),
      qty: 100,
      bookCost: 12000,
      pricePreContract: 100,
      completionCost: 500,
      sellingExpense: 300,
      relatedTax: 200,
    }
    const enriched = enrichImpairmentProduct(row)
    expect(enriched.nrv).toBeCloseTo(10000 - 500 - 300 - 200, 2)
    expect(enriched.requiredProvision).toBeCloseTo(3000, 2)
    expect(enriched.auditedAmount).toBeCloseTo(9000, 2)
    expect(enriched.bookUnitCost).toBeCloseTo(120, 2)
  })

  it('derives selling expense from rate when manual is zero', () => {
    const row = {
      ...emptyImpairmentProduct(),
      qty: 10,
      pricePreContract: 200,
      sellingExpenseRate: 5,
    }
    const enriched = enrichImpairmentProduct(row)
    expect(enriched.computedSellingExpense).toBeCloseTo(100, 2)
  })

  it('flags aging mismatch', () => {
    const row = {
      ...emptyImpairmentProduct(),
      qty: 100,
      aging: { within1y: 60, y1to2: 30, y2to3: 20, over3y: 0 },
    }
    expect(enrichImpairmentProduct(row).agingMismatch).toBe(true)
  })

  it('calculates additional provision vs booked', () => {
    const row = {
      ...emptyImpairmentProduct(),
      qty: 10,
      bookCost: 1000,
      pricePreContract: 50,
      bookedProvision: 100,
    }
    const enriched = enrichImpairmentProduct(row)
    expect(enriched.requiredProvision).toBeCloseTo(500, 2)
    expect(enriched.additionalProvision).toBeCloseTo(400, 2)
    expect(enriched.reversal).toBe(0)
  })

  it('column totals and category summaries', () => {
    const products = [
      { ...emptyImpairmentProduct(), category: '原材料', qty: 10, bookCost: 1000, pricePreContract: 100 },
      { ...emptyImpairmentProduct(), category: '原材料', qty: 5, bookCost: 800, pricePreContract: 200 },
      { ...emptyImpairmentProduct(), category: '产成品', qty: 2, bookCost: 500, pricePreContract: 300 },
    ]
    const enriched = enrichImpairmentProducts(products)
    const totals = calcImpairmentTotals(enriched)
    expect(totals.bookCost).toBeCloseTo(2300, 2)
    const cats = calcCategorySummaries(enriched)
    expect(cats).toHaveLength(2)
    const raw = cats.find((c) => c.category === '原材料')
    expect(raw?.bookCost).toBeCloseTo(1800, 2)
  })

  it('category summaries skip blank placeholder rows', () => {
    const products = [
      { ...emptyImpairmentProduct(), category: '原材料', qty: 10, bookCost: 1000, pricePreContract: 100 },
      emptyImpairmentProduct(),
      emptyImpairmentProduct(),
    ]
    const cats = calcCategorySummaries(enrichImpairmentProducts(products))
    expect(cats).toHaveLength(1)
    expect(cats[0].category).toBe('原材料')
  })

  it('pruneBlankProducts collapses reserved empty shells to one', () => {
    const blanks = Array.from({ length: 10 }, () => emptyImpairmentProduct())
    expect(pruneBlankProducts(blanks)).toHaveLength(1)

    const mixed = [
      { ...emptyImpairmentProduct(), itemName: '钢材', qty: 1, bookCost: 100 },
      emptyImpairmentProduct(),
      emptyImpairmentProduct(),
    ]
    const pruned = pruneBlankProducts(mixed)
    expect(pruned).toHaveLength(1)
    expect(pruned[0].itemName).toBe('钢材')
  })

  it('migrateImpairmentSheet prunes historical empty products', () => {
    const legacy = {
      sampling: { auditObject: '', sampleCriteria: '', samplingMethod: '', samplingProcess: '' },
      auditProcedure: '',
      products: Array.from({ length: 10 }, () => emptyImpairmentProduct()),
    }
    const sheet = migrateImpairmentSheet(legacy)
    expect(sheet?.products).toHaveLength(1)
  })

  it('migrates legacy flat rows', () => {
    const legacy = [{
      rowId: 'old-1',
      itemName: '钢材',
      qty: 10,
      unitCost: 100,
      sellingPrice: 90,
      completionCost: 50,
      sellingExpense: 20,
      tax: 10,
      existingProvision: 0,
      conclusion: '需补提',
    }]
    const sheet = migrateImpairmentSheet(legacy, '抽样说明')
    expect(sheet?.products[0].itemName).toBe('钢材')
    expect(sheet?.products[0].bookCost).toBe(1000)
    expect(sheet?.products[0].pricePreContract).toBe(90)
    expect(sheet?.products[0].remark).toBe('需补提')
    expect(sheet?.sampling.auditObject).toBe('抽样说明')
  })
})
