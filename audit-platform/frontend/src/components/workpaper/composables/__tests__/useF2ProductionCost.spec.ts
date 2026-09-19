/**
 * F2-41~44 生产成本组 — 公式单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  calcProductionPeriodEnd,
  enrichProductionRow,
  enrichLaborRow,
  type ProductionCostRow,
  type DirectLaborRow,
} from '../useF2ProductionCostFormulas'

describe('useF2ProductionCostFormulas', () => {
  it('periodEnd = opening + input - transfer', () => {
    expect(calcProductionPeriodEnd(100, 50, 30)).toBe(120)
    expect(calcProductionPeriodEnd(0, 200, 200)).toBe(0)
    expect(calcProductionPeriodEnd(500, 0, 100)).toBe(400)
  })

  it('enrichProductionRow computes dmClosing from periodEnd formula', () => {
    const row: ProductionCostRow = {
      rowId: 't1', productName: 'A',
      dmOpening: 100, dmInput: 40, dmTransfer: 10,
      dlOpening: 0, dlInput: 0, dlTransfer: 0,
      ohOpening: 0, ohInput: 0, ohTransfer: 0, remark: '',
    }
    const enriched = enrichProductionRow(row)
    expect(enriched.dmClosing).toBe(130)
    expect(enriched.totalClosing).toBe(130)
  })

  it('enrichLaborRow: calculatedLabor = headcount × hours × wageRate', () => {
    const row: DirectLaborRow = {
      rowId: 'l1', department: '车间', jobType: '操作',
      headcount: 10, hours: 8, wageRate: 25, actualLabor: 2100, remark: '',
    }
    const enriched = enrichLaborRow(row, 2000)
    expect(enriched.calculatedLabor).toBe(2000)
    expect(enriched.sharePct).toBeCloseTo(100, 1)
  })
})
