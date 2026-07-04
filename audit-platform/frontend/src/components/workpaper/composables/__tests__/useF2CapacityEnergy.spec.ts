import { describe, it, expect } from 'vitest'
import { enrichCapacityEnergyRow, type CapacityEnergyRow } from '../useF2CapacityEnergy'

function row(overrides: Partial<CapacityEnergyRow> = {}): CapacityEnergyRow {
  return {
    id: '1',
    productName: '产品A',
    productLine: '线1',
    designCapacity: 0, actualOutput: 0,
    elecTotal: 0, waterTotal: 0, gasTotal: 0,
    priorOutput: 0, priorElecTotal: 0, changeNote: '', auditFocus: '',
    ...overrides,
  }
}

describe('useF2CapacityEnergy enrichCapacityEnergyRow', () => {
  it('utilizationPct = actual / design × 100; N/A when design=0', () => {
    expect(enrichCapacityEnergyRow(row({ designCapacity: 100, actualOutput: 80 })).utilizationPct).toBe(80)
    expect(enrichCapacityEnergyRow(row({ designCapacity: 0, actualOutput: 80 })).utilizationPct).toBe('N/A')
  })

  it('unitElec = elecTotal / actualOutput; - when output=0', () => {
    expect(enrichCapacityEnergyRow(row({ actualOutput: 100, elecTotal: 500 })).unitElec).toBe(5)
    expect(enrichCapacityEnergyRow(row({ actualOutput: 0, elecTotal: 500 })).unitElec).toBe('-')
  })

  it('isOverCapacity when utilization > 100%; isEnergyAbnormal when elec change > 20%', () => {
    const over = enrichCapacityEnergyRow(row({ designCapacity: 100, actualOutput: 120 }))
    expect(over.isOverCapacity).toBe(true)
    expect(over.highlight).toBe(true)

    const energy = enrichCapacityEnergyRow(row({
      designCapacity: 100, actualOutput: 100, priorOutput: 100,
      elecTotal: 600, priorElecTotal: 400,
    }))
    expect(energy.isEnergyAbnormal).toBe(true)
  })
})
