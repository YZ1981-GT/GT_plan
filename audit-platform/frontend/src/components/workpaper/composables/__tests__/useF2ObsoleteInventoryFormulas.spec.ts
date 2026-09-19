import { describe, it, expect } from 'vitest'
import {
  defaultObsoleteSheet,
  enrichObsoleteItem,
  enrichObsoleteItems,
  calcObsoleteTotals,
  migrateObsoleteSheet,
  emptyObsoleteItem,
  hasImpairmentSign,
  isBlankObsoleteItem,
  pruneBlankObsoleteItems,
} from '../useF2ObsoleteInventoryFormulas'

describe('useF2ObsoleteInventoryFormulas', () => {
  it('default sheet has a single blank row', () => {
    const products = defaultObsoleteSheet().products
    expect(products).toHaveLength(1)
    expect(isBlankObsoleteItem(products[0])).toBe(true)
  })

  it('isBlankObsoleteItem detects any filled field', () => {
    expect(isBlankObsoleteItem(emptyObsoleteItem())).toBe(true)
    expect(isBlankObsoleteItem({ ...emptyObsoleteItem(), itemName: 'A' })).toBe(false)
    expect(isBlankObsoleteItem({ ...emptyObsoleteItem(), provisionAmount: 1 })).toBe(false)
    expect(isBlankObsoleteItem({
      ...emptyObsoleteItem(),
      aging: { within1y: 0, y1to2: 2, y2to3: 0, over3y: 0 },
    })).toBe(false)
  })

  it('pruneBlankObsoleteItems keeps filled rows only, or one blank shell', () => {
    const filled = { ...emptyObsoleteItem(), itemName: '原材料A', qty: 1 }
    const pruned = pruneBlankObsoleteItems([
      emptyObsoleteItem(), filled, emptyObsoleteItem(), emptyObsoleteItem(),
    ])
    expect(pruned).toHaveLength(1)
    expect(pruned[0].itemName).toBe('原材料A')

    const allBlank = pruneBlankObsoleteItems(Array.from({ length: 10 }, () => emptyObsoleteItem()))
    expect(allBlank).toHaveLength(1)
    expect(isBlankObsoleteItem(allBlank[0])).toBe(true)
  })

  it('migrateObsoleteSheet prunes historical reserved blank rows', () => {
    const legacySheet = {
      products: [
        { ...emptyObsoleteItem(), itemName: '呆滞B', qty: 5 },
        ...Array.from({ length: 9 }, () => emptyObsoleteItem()),
      ],
    }
    const sheet = migrateObsoleteSheet(legacySheet)
    expect(sheet?.products).toHaveLength(1)
    expect(sheet?.products[0].itemName).toBe('呆滞B')
  })

  it('calculates ending amount from qty and unit price', () => {
    const row = { ...emptyObsoleteItem(), qty: 100, unitPrice: 12.5 }
    expect(enrichObsoleteItem(row).endingAmount).toBeCloseTo(1250, 2)
  })

  it('flags aging mismatch when buckets do not sum to qty', () => {
    const row = {
      ...emptyObsoleteItem(),
      qty: 100,
      aging: { within1y: 60, y1to2: 30, y2to3: 20, over3y: 0 },
    }
    expect(enrichObsoleteItem(row).agingMismatch).toBe(true)
  })

  it('highlights long age and impairment signs', () => {
    const longAge = enrichObsoleteItem({
      ...emptyObsoleteItem(),
      qty: 10,
      aging: { within1y: 0, y1to2: 0, y2to3: 5, over3y: 5 },
    })
    expect(longAge.isLongAge).toBe(true)
    expect(longAge.highlight).toBe(true)

    const sign = enrichObsoleteItem({
      ...emptyObsoleteItem(),
      impairmentSigns: '呆滞',
    })
    expect(sign.hasImpairmentSign).toBe(true)
    expect(hasImpairmentSign('无')).toBe(false)
  })

  it('column totals sum correctly', () => {
    const products = [
      { ...emptyObsoleteItem(), qty: 10, unitPrice: 100, provisionAmount: 50,
        aging: { within1y: 10, y1to2: 0, y2to3: 0, over3y: 0 } },
      { ...emptyObsoleteItem(), qty: 5, unitPrice: 200, provisionAmount: 30,
        aging: { within1y: 0, y1to2: 5, y2to3: 0, over3y: 0 } },
    ]
    const enriched = enrichObsoleteItems(products)
    const totals = calcObsoleteTotals(enriched)
    expect(totals.qty).toBe(15)
    expect(totals.endingAmount).toBeCloseTo(2000, 2)
    expect(totals.provisionAmount).toBeCloseTo(80, 2)
    expect(totals.agingWithin1y).toBe(10)
    expect(totals.agingY1to2).toBe(5)
  })

  it('migrates legacy flat rows', () => {
    const legacy = [{
      rowId: 'old-1',
      itemName: '原材料A',
      qty: 50,
      bookCost: 5000,
      ageDays: 800,
      isObsolete: true,
      impairmentSuggestion: 200,
    }]
    const sheet = migrateObsoleteSheet(legacy)
    expect(sheet?.products[0].itemName).toBe('原材料A')
    expect(sheet?.products[0].unitPrice).toBe(100)
    expect(sheet?.products[0].aging.y2to3).toBe(50)
    expect(sheet?.products[0].impairmentSigns).toContain('呆滞')
    expect(sheet?.products[0].provisionAmount).toBe(200)
  })
})
