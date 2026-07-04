import { describe, it, expect } from 'vitest'
import { enrichUnitConsumptionRow, type UnitConsumptionRow } from '../useF2UnitConsumption'

function row(overrides: Partial<UnitConsumptionRow> = {}): UnitConsumptionRow {
  return {
    id: '1',
    productName: '产品A',
    materialName: '钢材',
    spec: 'Q235',
    unit: 'kg',
    standardConsumption: 0,
    actualConsumption: 0,
    inputQty: 0,
    outputQty: 0,
    priorConsumption: 0,
    consumptionT1: 0,
    consumptionT2: 0,
    materialUnitPrice: 0,
    rationalityNote: '',
    auditFocus: '',
    remark: '',
    ...overrides,
  }
}

describe('useF2UnitConsumption enrichUnitConsumptionRow', () => {
  it('deviationPct = (actual - standard) / standard × 100', () => {
    const enriched = enrichUnitConsumptionRow(row({ standardConsumption: 10, actualConsumption: 12 }))
    expect(enriched.deviationPct).toBeCloseTo(20, 5)
    expect(enriched.isHighDeviation).toBe(true)
  })

  it('ioRatio = input / output; flags imbalance outside 0.9~1.1', () => {
    const ok = enrichUnitConsumptionRow(row({ inputQty: 100, outputQty: 100 }))
    expect(ok.ioRatio).toBe(1)
    expect(ok.isIoImbalance).toBe(false)

    const bad = enrichUnitConsumptionRow(row({ inputQty: 130, outputQty: 100 }))
    expect(bad.isIoImbalance).toBe(true)
    expect(bad.warningLevel).toBe('io')
  })

  it('amountImpact = (actual - standard) × output × materialUnitPrice', () => {
    const enriched = enrichUnitConsumptionRow(row({
      standardConsumption: 10,
      actualConsumption: 12,
      outputQty: 1000,
      materialUnitPrice: 5,
    }))
    expect(enriched.amountImpact).toBe(10000)
  })
})
