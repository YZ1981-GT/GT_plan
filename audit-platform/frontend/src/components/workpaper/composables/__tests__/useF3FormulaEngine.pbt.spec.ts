/**
 * Property-Based Tests — F3 应付票据公式引擎
 *
 * Spec: .kiro/specs/f3-notes-payable/ Tasks 2.2 ~ 2.9
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcInterest,
  calcCreditBalance,
  calcAdjustedAmount,
  calcConcentration,
  isDebitCreditBalanced,
  calcOverdueDays,
} from '../useF3FormulaEngine'

describe('Feature: f3-notes-payable, Property 1: 应付利息公式', () => {
  it('calcInterest(principal, rate, days) === principal × rate/100 × days/360', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true }),
        fc.nat({ max: 3650 }),
        (principal, rate, days) => {
          const result = calcInterest(principal, rate, days)
          const expected = (principal * rate / 100 * days) / 360
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when principal or days is negative', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true }),
        (principal, rate) => {
          expect(calcInterest(-1, rate, 30)).toBe(0)
          expect(calcInterest(principal, rate, -1)).toBe(0)
        },
      ),
      { numRuns: 50 },
    )
  })
})

describe('Feature: f3-notes-payable, Property 2: 贷方余额公式', () => {
  it('calcCreditBalance === opening + credit - debit', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (opening, credit, debit) => {
          expect(calcCreditBalance(opening, credit, debit)).toBeCloseTo(opening + credit - debit, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f3-notes-payable, Property 3: 审定数公式', () => {
  it('calcAdjustedAmount === unadjusted + aje + rje', () => {
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

describe('Feature: f3-notes-payable, Property 4: 借贷平衡', () => {
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

describe('Feature: f3-notes-payable, Property 5: 集中度公式', () => {
  it('calcConcentration === amount/total × 100 when total > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (amount, total) => {
          expect(calcConcentration(amount, total)).toBeCloseTo((amount / total) * 100, 4)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when total is 0', () => {
    expect(calcConcentration(100, 0)).toBe(0)
  })
})

describe('Feature: f3-notes-payable, Property 6: 逾期天数非负', () => {
  it('calcOverdueDays >= 0 for any due date', () => {
    fc.assert(
      fc.property(fc.date(), fc.date(), (due, asOf) => {
        if (Number.isNaN(due.getTime()) || Number.isNaN(asOf.getTime())) return
        const dueStr = due.toISOString().slice(0, 10)
        expect(calcOverdueDays(dueStr, asOf)).toBeGreaterThanOrEqual(0)
      }),
      { numRuns: 100 },
    )
  })

  it('returns 0 for empty due date', () => {
    expect(calcOverdueDays('')).toBe(0)
  })
})

describe('Feature: f3-notes-payable, Property 7: 利息与面值正比', () => {
  it('calcInterest(p1)/calcInterest(p2) ≈ p1/p2', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.1, max: 20, noNaN: true, noDefaultInfinity: true }),
        fc.nat({ max: 360 }),
        (p1, p2, rate, days) => {
          const i1 = calcInterest(p1, rate, days)
          const i2 = calcInterest(p2, rate, days)
          if (i2 < 1e-6) return
          expect(i1 / i2).toBeCloseTo(p1 / p2, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f3-notes-payable, Property 8: 贷方余额方向性', () => {
  it('credit > debit → balance > opening', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (opening, extra) => {
          const credit = extra + 1
          const debit = extra
          expect(calcCreditBalance(opening, credit, debit)).toBeGreaterThan(opening)
        },
      ),
      { numRuns: 100 },
    )
  })
})
