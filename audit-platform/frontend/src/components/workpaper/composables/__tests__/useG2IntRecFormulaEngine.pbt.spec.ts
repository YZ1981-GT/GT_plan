/**
 * Property-Based Tests — G2 应收利息公式引擎
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Tasks 2.2 ~ 2.11
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcInterest365,
  calcDebitBalance,
  calcAdjustedAmount,
  calcECL,
  calcOverdueDays,
  isDebitCreditBalanced,
  determineStage,
  calcNetReceivable,
} from '../useG2IntRecFormulaEngine'

describe('Feature: g2-interest-receivable, Property 1: 利息测算公式(365天)', () => {
  it('calcInterest365(principal, rate, days) ≈ principal × rate/100 × days/365', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true }),
        fc.nat({ max: 3650 }),
        (principal, rate, days) => {
          const result = calcInterest365(principal, rate, days)
          const expected = (principal * rate / 100 * days) / 365
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
          expect(calcInterest365(-1, rate, 30)).toBe(0)
          expect(calcInterest365(principal, rate, -1)).toBe(0)
        },
      ),
      { numRuns: 50 },
    )
  })
})

describe('Feature: g2-interest-receivable, Property 2: 借方余额公式', () => {
  it('calcDebitBalance === opening + debit - credit', () => {
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

describe('Feature: g2-interest-receivable, Property 3: 审定数公式', () => {
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

describe('Feature: g2-interest-receivable, Property 4: ECL公式', () => {
  it('calcECL(EAD, PD, LGD) ≈ EAD × PD × LGD', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        (ead, pd, lgd) => {
          expect(calcECL(ead, pd, lgd)).toBeCloseTo(ead * pd * lgd, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when any parameter is negative', () => {
    expect(calcECL(-1, 0.5, 0.5)).toBe(0)
    expect(calcECL(1000, -0.1, 0.5)).toBe(0)
    expect(calcECL(1000, 0.5, -0.1)).toBe(0)
  })
})

describe('Feature: g2-interest-receivable, Property 5: 逾期天数非负', () => {
  it('calcOverdueDays >= 0 for any due date', () => {
    fc.assert(
      fc.property(fc.date({ noInvalidDate: true }), fc.date({ noInvalidDate: true }), (due, asOf) => {
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

describe('Feature: g2-interest-receivable, Property 6: 借贷平衡恒等', () => {
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

describe('Feature: g2-interest-receivable, Property 7: 利息与面值正比', () => {
  it('calcInterest365(p1)/calcInterest365(p2) ≈ p1/p2', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.1, max: 20, noNaN: true, noDefaultInfinity: true }),
        fc.nat({ max: 365 }),
        (p1, p2, rate, days) => {
          const i1 = calcInterest365(p1, rate, days)
          const i2 = calcInterest365(p2, rate, days)
          if (i2 < 1e-6) return
          expect(i1 / i2).toBeCloseTo(p1 / p2, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g2-interest-receivable, Property 8: ECL与EAD正比', () => {
  it('calcECL(e1)/calcECL(e2) ≈ e1/e2', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1, noNaN: true, noDefaultInfinity: true }),
        (e1, e2, pd, lgd) => {
          const ecl1 = calcECL(e1, pd, lgd)
          const ecl2 = calcECL(e2, pd, lgd)
          if (ecl2 < 1e-6) return
          expect(ecl1 / ecl2).toBeCloseTo(e1 / e2, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g2-interest-receivable, Property 9: 阶段判定确定性', () => {
  it('determineStage ∈ {1,2,3} with priority impaired>significantIncrease>normal', () => {
    fc.assert(
      fc.property(fc.boolean(), fc.boolean(), (impaired, significantIncrease) => {
        const stage = determineStage(impaired, significantIncrease)
        expect([1, 2, 3]).toContain(stage)
        if (impaired) expect(stage).toBe(3)
        else if (significantIncrease) expect(stage).toBe(2)
        else expect(stage).toBe(1)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g2-interest-receivable, Property 10: 净应收=应计-已收', () => {
  it('calcNetReceivable(accrued, received) === accrued - received', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (accrued, received) => {
          expect(calcNetReceivable(accrued, received)).toBeCloseTo(accrued - received, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
