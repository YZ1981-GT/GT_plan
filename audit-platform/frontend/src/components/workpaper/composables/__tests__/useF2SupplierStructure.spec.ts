import { describe, it, expect } from 'vitest'
import {
  enrichSupplierRow,
  type SupplierStructureRow,
} from '../useF2SupplierStructure'

function baseRow(overrides: Partial<SupplierStructureRow> = {}): SupplierStructureRow {
  return {
    id: '1',
    supplierName: '供应商A',
    category: '原材料',
    coopYear: '2020',
    isRelated: '否',
    amountT: 0,
    amountT1: 0,
    amountT2: 0,
    concentrationEval: '',
    indexNo: '',
    remark: '',
    ...overrides,
  }
}

describe('useF2SupplierStructure enrichSupplierRow', () => {
  it('ratioT = amountT / totalT × 100', () => {
    const r = baseRow({ amountT: 400 })
    const enriched = enrichSupplierRow(r, 1000, 800, 600, 1, 1, 1)
    expect(enriched.ratioT).toBe(40)
  })

  it('entryFlag: 新增 when T>0 and T-1=0; 退出 when T=0 and T-1>0', () => {
    expect(enrichSupplierRow(baseRow({ amountT: 100 }), 100, 0, 0, 1, 0, 0).entryFlag).toBe('新增')
    expect(enrichSupplierRow(baseRow({ amountT1: 100 }), 100, 100, 0, 0, 1, 0).entryFlag).toBe('退出')
  })

  it('isNewTop5 and highlight when new entry ranks in top 5 with high concentration', () => {
    const r = baseRow({ amountT: 350 })
    const enriched = enrichSupplierRow(r, 1000, 500, 400, 3, 0, 0)
    expect(enriched.isNewTop5).toBe(true)
    expect(enriched.highlight).toBe(true)
    expect(enriched.isHighConcentration).toBe(true)
  })
})
