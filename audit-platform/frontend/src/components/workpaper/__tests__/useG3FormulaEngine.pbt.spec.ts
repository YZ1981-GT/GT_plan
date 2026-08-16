/**
 * Property-Based Tests — G3 应收股利公式引擎
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Tasks 2.2 ~ 2.11
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcDividend,
  calcDebitBalance,
  calcAdjustedAmount,
  calcOverdueDays,
  isDebitCreditBalanced,
  calcPayoutRatio,
  calcNetReceivable,
  calcEquityShare,
} from '../composables/useG3DivRecFormulaEngine'

describe('Feature: g3-dividend-receivable, Property 1: 股利测算公式', () => {
  /**
   * **Validates: Requirements 9.1, 5.3, 5.5, 7.2**
   * ∀ shares ∈ ℤ≥0, dps ∈ ℝ≥0: calcDividend(shares, dps) === shares × dps
   */
  it('calcDividend(shares, dps) === shares × dps', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 100000000 }),
        fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true }),
        (shares, dps) => {
          const result = calcDividend(shares, dps)
          const expected = shares * dps
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 2: 借方余额公式', () => {
  /**
   * **Validates: Requirements 9.3, 3.3**
   * ∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit
   */
  it('calcDebitBalance(opening, debit, credit) === opening + debit - credit', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (opening, debit, credit) => {
          expect(calcDebitBalance(opening, debit, credit)).toBeCloseTo(opening + debit - credit, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 3: 审定数公式', () => {
  /**
   * **Validates: Requirements 9.4, 3.4**
   * ∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
   */
  it('calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (unadjusted, aje, rje) => {
          expect(calcAdjustedAmount(unadjusted, aje, rje)).toBeCloseTo(unadjusted + aje + rje, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 4: 逾期天数非负', () => {
  /**
   * **Validates: Requirements 9.5, 8.2**
   * ∀ currentDate, dueDate: calcOverdueDays(currentDate, dueDate) ≥ 0
   */
  it('calcOverdueDays(currentDate, dueDate) >= 0 for any dates', () => {
    fc.assert(
      fc.property(fc.date({ noInvalidDate: true }), fc.date({ noInvalidDate: true }), (currentDate, dueDate) => {
        if (Number.isNaN(currentDate.getTime()) || Number.isNaN(dueDate.getTime())) return
        expect(calcOverdueDays(currentDate, dueDate)).toBeGreaterThanOrEqual(0)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 5: 借贷平衡恒等', () => {
  /**
   * **Validates: Requirements 9.8, 6.2**
   * ∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
   */
  it('isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 20 }),
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 20 }),
        (debits, credits) => {
          const d = debits.reduce((s, v) => s + v, 0)
          const c = credits.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(debits, credits)).toBe(Math.abs(d - c) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 6: 分红率与分红总额正比', () => {
  /**
   * **Validates: Requirements 9.2, 5.4**
   * ∀ d1, d2 ∈ ℝ≥0, d2≠0, netProfit>0固定: calcPayoutRatio(d1, np)/calcPayoutRatio(d2, np) ≈ d1/d2
   */
  it('calcPayoutRatio(d1, np) / calcPayoutRatio(d2, np) ≈ d1/d2', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (d1, d2, netProfit) => {
          const r1 = calcPayoutRatio(d1, netProfit)
          const r2 = calcPayoutRatio(d2, netProfit)
          if (r2 < 1e-9) return
          expect(r1 / r2).toBeCloseTo(d1 / d2, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 7: 股利与持股数正比', () => {
  /**
   * **Validates: Requirements 9.1, 5.3**
   * ∀ s1, s2 ∈ ℤ>0, dps固定: calcDividend(s1, dps)/calcDividend(s2, dps) ≈ s1/s2
   */
  it('calcDividend(s1, dps) / calcDividend(s2, dps) ≈ s1/s2', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100000000 }),
        fc.integer({ min: 1, max: 100000000 }),
        fc.double({ min: 0.01, max: 100, noNaN: true, noDefaultInfinity: true }),
        (s1, s2, dps) => {
          const div1 = calcDividend(s1, dps)
          const div2 = calcDividend(s2, dps)
          if (div2 < 1e-9) return
          expect(div1 / div2).toBeCloseTo(s1 / s2, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 8: 净应收=应收-已收', () => {
  /**
   * **Validates: Requirements 9.6, 5.6**
   * ∀ receivable ∈ ℝ≥0, received ∈ ℝ≥0: calcNetReceivable(receivable, received) === receivable - received
   */
  it('calcNetReceivable(receivable, received) === receivable - received', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (receivable, received) => {
          expect(calcNetReceivable(receivable, received)).toBeCloseTo(receivable - received, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 9: 权益份额公式', () => {
  /**
   * **Validates: Requirements 9.7, 5.2**
   * ∀ netAssets ∈ ℝ, ratio ∈ [0,100]: calcEquityShare(netAssets, ratio) === netAssets × ratio/100
   */
  it('calcEquityShare(netAssets, ratio) === netAssets × ratio/100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true }),
        (netAssets, ratio) => {
          expect(calcEquityShare(netAssets, ratio)).toBeCloseTo(netAssets * ratio / 100, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g3-dividend-receivable, Property 10: 分红率非负', () => {
  /**
   * **Validates: Requirements 9.2**
   * ∀ dividendTotal ∈ ℝ≥0, netProfit ∈ ℝ>0: calcPayoutRatio(dividendTotal, netProfit) ≥ 0
   */
  it('calcPayoutRatio(dividendTotal, netProfit) >= 0 when netProfit > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (dividendTotal, netProfit) => {
          expect(calcPayoutRatio(dividendTotal, netProfit)).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})
