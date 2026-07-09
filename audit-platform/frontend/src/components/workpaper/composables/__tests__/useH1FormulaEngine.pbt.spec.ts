/**
 * Property-Based Tests — H1 固定资产公式引擎
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Tasks 2.3 ~ 2.7, 2.17 ~ 2.19
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcDisposalGainLoss,
  calcLeaseReturnRate,
  calcTitleDiff,
} from '../useH1FormulaEngine'

describe('Feature: h1-fixed-assets, Property P1: 资产类审定数公式链正确性', () => {
  /**
   * **Validates: Requirements 1.5, 2.3**
   * ∀ unadj, aje, rje ∈ ℝ: calcAuditedAmount(unadj, aje, rje) === unadj + aje + rje
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (unadj, aje, rje) => {
          const result = calcAuditedAmount(unadj, aje, rje)
          const expected = unadj + aje + rje
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: h1-fixed-assets, Property P2: 资产类期末余额公式（借方科目）', () => {
  /**
   * **Validates: Requirements 2.4**
   * ∀ begin, debit, credit ∈ ℝ≥0: calcAssetEndBalance(begin, debit, credit) === begin + debit - credit
   */
  it('calcAssetEndBalance(b, d, c) === b + d - c', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, debit, credit) => {
          const result = calcAssetEndBalance(begin, debit, credit)
          const expected = begin + debit - credit
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: h1-fixed-assets, Property P3: 备抵类期末余额公式（贷方科目）', () => {
  /**
   * **Validates: Requirements 2.5**
   * ∀ begin, debit, credit ∈ ℝ≥0: calcContraEndBalance(begin, debit, credit) === begin + credit - debit
   */
  it('calcContraEndBalance(b, d, c) === b + c - d', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, debit, credit) => {
          const result = calcContraEndBalance(begin, debit, credit)
          const expected = begin + credit - debit
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: h1-fixed-assets, Property P4: 三角勾稽恒等式', () => {
  /**
   * **Validates: Requirements 2.7**
   * ∀ begin, increase, decrease ∈ ℝ≥0, end=begin+increase-decrease:
   * calcTriangleReconciliation(begin, increase, decrease, end) === 0
   */
  it('calcTriangleReconciliation(b, i, d, b+i-d) === 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, increase, decrease) => {
          const end = begin + increase - decrease
          const result = calcTriangleReconciliation(begin, increase, decrease, end)
          expect(Math.abs(result)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: h1-fixed-assets, Property P5: 合计行恒等于明细行之和', () => {
  /**
   * **Validates: Requirements 2.6**
   * ∀ arr: number[] (len≥1): calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
   */
  it('calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: h1-fixed-assets, Property P15: 处置损益公式正确性', () => {
  /**
   * **Validates: Requirements 9.3**
   * ∀ income, netValue, disposalCost ≥ 0: calcDisposalGainLoss(inc, nv, cost) === inc - nv - cost
   */
  it('calcDisposalGainLoss(inc, nv, cost) === inc - nv - cost', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (income, netValue, disposalCost) => {
          const result = calcDisposalGainLoss(income, netValue, disposalCost)
          const expected = income - netValue - disposalCost
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: h1-fixed-assets, Property P16: 经营租出收益率公式', () => {
  /**
   * **Validates: Requirements 15.5**
   * ∀ netIncome ∈ ℝ, cost > 0: calcLeaseReturnRate(ni, c) === ni/c × 100
   */
  it('calcLeaseReturnRate(ni, c) === ni / c * 100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (netIncome, cost) => {
          const result = calcLeaseReturnRate(netIncome, cost)
          const expected = netIncome / cost * 100
          expect(Math.abs(result! - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: h1-fixed-assets, Property P17: 权属差异=账面-证载', () => {
  /**
   * **Validates: Requirements 14.7**
   * ∀ bookValue, certValue ≥ 0: calcTitleDiff(b, c) === b - c
   */
  it('calcTitleDiff(b, c) === b - c', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (bookValue, certValue) => {
          const result = calcTitleDiff(bookValue, certValue)
          const expected = bookValue - certValue
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})
