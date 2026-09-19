import { describe, it, expect } from 'vitest'
import {
  defaultPurchasePriceSheet,
  emptyPurchaseMaterial,
  isBlankPurchaseMaterial,
  pruneBlankPurchaseMaterials,
  calcPurchaseUnitPrice,
  enrichPurchaseMaterial,
  enrichPurchaseMaterials,
  calcPurchasePriceTotals,
  migratePurchasePriceSheet,
} from '../useF2PurchasePriceFormulas'

function materialWith(patch: Partial<ReturnType<typeof emptyPurchaseMaterial>>) {
  return { ...emptyPurchaseMaterial(), ...patch }
}

describe('useF2PurchasePriceFormulas', () => {
  it('default sheet keeps one editable material row', () => {
    const materials = defaultPurchasePriceSheet().materials
    expect(materials).toHaveLength(1)
    expect(isBlankPurchaseMaterial(materials[0])).toBe(true)
  })

  it('prunes reserved blank rows but retains entered materials', () => {
    const entered = materialWith({ materialName: '钢材' })
    expect(pruneBlankPurchaseMaterials([
      emptyPurchaseMaterial(),
      entered,
      emptyPurchaseMaterial(),
    ])).toEqual([entered])
  })

  it('keeps one blank row when all rows are empty', () => {
    const rows = pruneBlankPurchaseMaterials([emptyPurchaseMaterial(), emptyPurchaseMaterial()])
    expect(rows).toHaveLength(1)
    expect(isBlankPurchaseMaterial(rows[0])).toBe(true)
  })

  it('unit price = amount / qty, null when qty is 0', () => {
    expect(calcPurchaseUnitPrice(1000, 100)).toBe(10)
    expect(calcPurchaseUnitPrice(1000, 0)).toBeNull()
  })

  it('enriches monthly unit prices and current totals/avg', () => {
    const row = emptyPurchaseMaterial()
    row.months[0] = { amount: 1000, qty: 100, marketPrice: 10 }
    row.months[1] = { amount: 2400, qty: 200, marketPrice: 11 }
    const e = enrichPurchaseMaterial(row)
    expect(e.enrichedMonths[0].unitPrice).toBe(10)
    expect(e.enrichedMonths[1].unitPrice).toBe(12)
    expect(e.currentTotalAmount).toBe(3400)
    expect(e.currentTotalQty).toBe(300)
    expect(e.currentAvgPrice).toBeCloseTo(3400 / 300, 6)
    expect(e.currentAvgMarketPrice).toBeCloseTo(10.5, 6)
  })

  it('flags monthly price abnormal beyond ±30% of current average', () => {
    const row = emptyPurchaseMaterial()
    // 平均约 10：1月单价 10，2月单价 20（偏离 +100% > 30%）
    row.months[0] = { amount: 10000, qty: 1000, marketPrice: 0 }
    row.months[1] = { amount: 400, qty: 20, marketPrice: 0 }
    const e = enrichPurchaseMaterial(row)
    expect(e.enrichedMonths[1].priceAbnormal).toBe(true)
    expect(e.hasMonthlyVariance).toBe(true)
  })

  it('flags market diff beyond ±10%', () => {
    const row = emptyPurchaseMaterial()
    row.months[0] = { amount: 1200, qty: 100, marketPrice: 10 } // 采购12 vs 市场10 = +20%
    const e = enrichPurchaseMaterial(row)
    expect(e.marketDiffRate).toBeCloseTo(0.2, 6)
    expect(e.hasMarketDiff).toBe(true)
  })

  it('prior averages derive from prior totals and prior end', () => {
    const row = materialWith({
      priorTotalAmount: 5000,
      priorTotalQty: 500,
      priorEnd: { amount: 900, qty: 100, marketPrice: 9.5 },
    })
    const e = enrichPurchaseMaterial(row)
    expect(e.priorAvgPrice).toBe(10)
    expect(e.priorEndUnitPrice).toBe(9)
  })

  it('column totals aggregate with weighted avg subtotal price', () => {
    const a = emptyPurchaseMaterial()
    a.months[0] = { amount: 1000, qty: 100, marketPrice: 10 }
    const b = emptyPurchaseMaterial()
    b.months[0] = { amount: 3000, qty: 100, marketPrice: 20 }
    const totals = calcPurchasePriceTotals(enrichPurchaseMaterials([a, b]))
    expect(totals.monthAmounts[0]).toBe(4000)
    expect(totals.monthQtys[0]).toBe(200)
    expect(totals.monthUnitPrices[0]).toBe(20)
    expect(totals.monthMarketAvgs[0]).toBe(15)
    expect(totals.currentTotalAmount).toBe(4000)
    expect(totals.currentAvgPrice).toBe(20)
  })

  it('migrates legacy flat rows (spec merged into name, priorAvgPrice → market avg)', () => {
    const legacy = [{
      id: 'r1',
      materialName: '铜材',
      spec: 'T2',
      unit: '吨',
      months: Array.from({ length: 12 }, (_, i) => ({ amount: i === 0 ? 100 : 0, qty: i === 0 ? 10 : 0 })),
      priorAvgPrice: 9.8,
    }]
    const sheet = migratePurchasePriceSheet(legacy)
    expect(sheet.materials).toHaveLength(1)
    expect(sheet.materials[0].materialName).toBe('铜材 T2')
    expect(sheet.materials[0].unit).toBe('吨')
    expect(sheet.materials[0].months[0]).toEqual({ amount: 100, qty: 10, marketPrice: 0 })
    expect(sheet.materials[0].priorAvgMarketPrice).toBe(9.8)
  })

  it('migrates new sheet JSON and prunes blank rows', () => {
    const entered = materialWith({ materialName: '钢材' })
    const sheet = migratePurchasePriceSheet({
      materials: [emptyPurchaseMaterial(), entered],
    })
    expect(sheet.materials.map((m) => m.materialName)).toEqual(['钢材'])
  })
})
