import { describe, it, expect } from 'vitest'
import {
  defaultAllocationSheet,
  effectivePool,
  enrichAllocationProducts,
  calcAllocationTotals,
  migrateAllocationSheet,
  poolGrandTotal,
  emptyAllocationProduct,
} from '../useF2CostAllocationFormulas'

describe('useF2CostAllocationFormulas', () => {
  it('default sheet has 12 product rows', () => {
    const s = defaultAllocationSheet()
    expect(s.products).toHaveLength(12)
    expect(s.pool.linkSource).toBe(true)
  })

  it('allocates by allocation base ratio', () => {
    const pool = { material: 1000, labor: 500, overhead: 300, other: 200, linkSource: false }
    const products = [
      { ...emptyAllocationProduct(), id: 'a', productName: 'A', outputQty: 100, bookUnitCost: 20, allocationBase: 60 },
      { ...emptyAllocationProduct(), id: 'b', productName: 'B', outputQty: 50, bookUnitCost: 30, allocationBase: 40 },
    ]
    const enriched = enrichAllocationProducts(products, pool)
    expect(enriched[0].materialRate).toBeCloseTo(60, 1)
    expect(enriched[0].materialAmt).toBeCloseTo(600, 2)
    expect(enriched[0].laborAmt).toBeCloseTo(300, 2)
    expect(enriched[0].totalAlloc).toBeCloseTo(1200, 2)
    expect(enriched[0].accruedUnitCost).toBeCloseTo(12, 2)
    expect(enriched[1].materialAmt).toBeCloseTo(400, 2)
    expect(enriched[1].totalAlloc).toBeCloseTo(800, 2)
    expect(enriched[1].accruedUnitCost).toBeCloseTo(16, 2)
  })

  it('column totals match pool when bases sum positive', () => {
    const pool = { material: 800, labor: 400, overhead: 200, other: 100, linkSource: false }
    const products = [
      { ...emptyAllocationProduct(), allocationBase: 30, outputQty: 10 },
      { ...emptyAllocationProduct(), allocationBase: 70, outputQty: 20 },
    ]
    const enriched = enrichAllocationProducts(products, pool)
    const totals = calcAllocationTotals(enriched)
    expect(totals.materialAmt).toBeCloseTo(800, 2)
    expect(totals.laborAmt).toBeCloseTo(400, 2)
    expect(totals.overheadAmt).toBeCloseTo(200, 2)
    expect(totals.otherAmt).toBeCloseTo(100, 2)
    expect(totals.totalAlloc).toBeCloseTo(poolGrandTotal(pool), 2)
  })

  it('verify OK when accrued matches book unit cost', () => {
    const pool = { material: 1000, labor: 0, overhead: 0, other: 0, linkSource: false }
    const products = [
      { ...emptyAllocationProduct(), allocationBase: 100, outputQty: 10, bookUnitCost: 100 },
    ]
    const [row] = enrichAllocationProducts(products, pool)
    expect(row.accruedUnitCost).toBeCloseTo(100, 2)
    expect(row.verify).toBe('OK')
    expect(row.verifyOk).toBe(true)
  })

  it('verify flags mismatch', () => {
    const pool = { material: 1000, labor: 0, overhead: 0, other: 0, linkSource: false }
    const products = [
      { ...emptyAllocationProduct(), allocationBase: 100, outputQty: 10, bookUnitCost: 80 },
    ]
    const [row] = enrichAllocationProducts(products, pool)
    expect(row.verifyOk).toBe(false)
    expect(row.verify).toMatch(/^差/)
  })

  it('effectivePool pulls from source when linkSource and pool zero', () => {
    const pool = { material: 0, labor: 0, overhead: 0, other: 50, linkSource: true }
    const effective = effectivePool(pool, { material: 100, labor: 200, overhead: 300 })
    expect(effective.material).toBe(100)
    expect(effective.labor).toBe(200)
    expect(effective.overhead).toBe(300)
    expect(effective.other).toBe(50)
  })

  it('effectivePool keeps manual override when non-zero', () => {
    const pool = { material: 999, labor: 0, overhead: 0, other: 0, linkSource: true }
    const effective = effectivePool(pool, { material: 100, labor: 200, overhead: 300 })
    expect(effective.material).toBe(999)
    expect(effective.labor).toBe(200)
  })

  it('migrates legacy flat AllocationRow array', () => {
    const legacy = [
      { productName: '产品A', allocationBase: 100 },
      { productName: '产品B', allocationBase: 200 },
    ]
    const migrated = migrateAllocationSheet(legacy)
    expect(migrated).not.toBeNull()
    expect(migrated!.products).toHaveLength(2)
    expect(migrated!.products[0].productName).toBe('产品A')
    expect(migrated!.products[0].allocationBase).toBe(100)
  })

  it('passes through new sheet format', () => {
    const sheet = defaultAllocationSheet()
    sheet.sampleMonth = '12月'
    expect(migrateAllocationSheet(sheet)).toEqual(sheet)
  })

  it('migrates imported flat rows with full product fields and numeric strings', () => {
    const imported = [
      { id: 'r1', productName: '产品A', outputQty: '100', bookUnitCost: '12.5', allocationBase: '60', baseNote: '工时' },
      { productName: '产品B', outputQty: 50, bookUnitCost: 30, allocationBase: 40, baseNote: '' },
    ]
    const migrated = migrateAllocationSheet(imported)
    expect(migrated).not.toBeNull()
    expect(migrated!.products).toHaveLength(2)
    expect(migrated!.products[0]).toMatchObject({
      id: 'r1', productName: '产品A', outputQty: 100, bookUnitCost: 12.5, allocationBase: 60, baseNote: '工时',
    })
    expect(migrated!.products[1].id).toBeTruthy()
    expect(migrated!.products[1].outputQty).toBe(50)
  })

  it('object payload with imported products keeps pool defaults and coerces rows', () => {
    const payload = {
      sampleMonth: '11月',
      products: [{ productName: 'X', outputQty: '10', bookUnitCost: '2', allocationBase: '5', baseNote: '产量' }],
    }
    const migrated = migrateAllocationSheet(payload)
    expect(migrated).not.toBeNull()
    expect(migrated!.sampleMonth).toBe('11月')
    expect(migrated!.workshop).toBe('')
    expect(migrated!.pool.linkSource).toBe(true)
    expect(migrated!.products[0].allocationBase).toBe(5)
  })
})
