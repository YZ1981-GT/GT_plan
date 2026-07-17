import { describe, it, expect } from 'vitest'
import {
  calcPeriodAmort,
  calcCumulativeAmort,
  enrichAmortizationRows,
  sumCapitalization,
  isContractCostTestExampleSheet,
  CAPITALIZATION_EXAMPLE_ROWS,
  AMORTIZATION_EXAMPLE_ROWS,
} from '../../f2-special/contract/f2ContractCostTestExampleData'

describe('f2ContractCostTestExampleData', () => {
  it('detects example sheet name', () => {
    expect(isContractCostTestExampleSheet('合同履约成本测试（示例）')).toBe(true)
    expect(isContractCostTestExampleSheet('F2-56 检查表')).toBe(false)
  })

  it('sums capitalization example', () => {
    expect(sumCapitalization(CAPITALIZATION_EXAMPLE_ROWS)).toBe(350000)
  })

  it('calculates period amortization', () => {
    expect(calcPeriodAmort(50000, 60, 24, 12)).toBeCloseTo(10000, 2)
  })

  it('calculates cumulative amortization', () => {
    expect(calcCumulativeAmort(50000, 60, 24)).toBeCloseTo(20000, 2)
  })

  it('enriches amortization rows with variances', () => {
    const rows = enrichAmortizationRows(AMORTIZATION_EXAMPLE_ROWS)
    expect(rows[0].testedPeriodAmort).toBeCloseTo(10000, 2)
    expect(rows[0].periodVariance).toBe(0)
  })
})
