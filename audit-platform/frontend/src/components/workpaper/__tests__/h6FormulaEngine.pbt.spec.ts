/**
 * Property-Based Tests — H6 固定资产清理公式引擎
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/ Tasks 2.2 ~ 2.6
 * Framework: fast-check (fc.assert + fc.property)
 * numRuns: 100
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcNetBookValue,
  calcDisposalGainLoss,
  calcSubtotal,
  isTransitBalanceZero,
} from '../composables/useH6FormulaEngine'

// ============================================================
// P1 (Task 2.2): 审定数公式链
// ============================================================
describe('Feature: h6-asset-disposal-clearing, Property P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.3**
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

// ============================================================
// P2 (Task 2.3): 资产类期末余额
// ============================================================
describe('Feature: h6-asset-disposal-clearing, Property P2: 资产类期末余额', () => {
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

// ============================================================
// P3 (Task 2.4): 清理净损益
// ============================================================
describe('Feature: h6-asset-disposal-clearing, Property P3: 清理净损益公式', () => {
  /**
   * **Validates: Requirements 3.2**
   * ∀ income, netValue, expenses, tax ∈ ℝ≥0:
   * calcDisposalGainLoss(i, nv, e, t) === i - nv - e - t
   */
  it('calcDisposalGainLoss(i, nv, e, t) === i - nv - e - t', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (income, netValue, expenses, tax) => {
          const result = calcDisposalGainLoss(income, netValue, expenses, tax)
          const expected = income - netValue - expenses - tax
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P4 (Task 2.5): 过渡科目零余额判定
// ============================================================
describe('Feature: h6-asset-disposal-clearing, Property P4: 过渡科目零余额判定', () => {
  /**
   * **Validates: Requirements 2.5**
   * isTransitBalanceZero(0) === true
   * ∀ x ∈ ℝ, x≠0: isTransitBalanceZero(x) === false
   */
  it('isTransitBalanceZero(0) === true', () => {
    expect(isTransitBalanceZero(0)).toBe(true)
  })

  it('isTransitBalanceZero(nonZero) === false', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }).filter(x => x !== 0),
        (balance) => {
          expect(isTransitBalanceZero(balance)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ============================================================
// P5 (Task 2.6): 净账面价值
// ============================================================
describe('Feature: h6-asset-disposal-clearing, Property P5: 净账面价值公式', () => {
  /**
   * **Validates: Requirements 2.6**
   * ∀ cost, dep ∈ ℝ≥0: calcNetBookValue(cost, dep) === cost - dep
   */
  it('calcNetBookValue(cost, dep) === cost - dep', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (cost, dep) => {
          const result = calcNetBookValue(cost, dep)
          const expected = cost - dep
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 100 },
    )
  })
})
