import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcCreditBalance,
  calcAdjustedAmount,
  calcChangeRate,
  calcL3Reconciliation,
  isDebitCreditBalanced,
} from '../useG10FormulaEngine'

describe('useG10FormulaEngine', () => {
  it('Property 1: calcCreditBalance(opening, credit, debit) === opening + credit - debit', () => {
    fc.assert(fc.property(
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      (opening, credit, debit) => {
        const o = Number.isFinite(opening) ? opening : 0
        const c = Number.isFinite(credit) ? credit : 0
        const d = Number.isFinite(debit) ? debit : 0
        expect(calcCreditBalance(o, c, d)).toBeCloseTo(o + c - d, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property 2: calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment', () => {
    fc.assert(fc.property(fc.float(), fc.float(), (u, a) => {
      const uu = Number.isFinite(u) ? u : 0
      const aa = Number.isFinite(a) ? a : 0
      expect(calcAdjustedAmount(uu, aa)).toBeCloseTo(uu + aa, 5)
    }), { numRuns: 50 })
  })

  it('Property 3: calcL3Reconciliation 8-parameter identity', () => {
    fc.assert(fc.property(
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      (o, n, t, ti, to, fv, int, other) => {
        const vals = [o, n, t, ti, to, fv, int, other].map(v => (Number.isFinite(v) ? v : 0))
        const expected = vals[0] + vals[1] - vals[2] + vals[3] - vals[4] + vals[5] + vals[6] + vals[7]
        expect(calcL3Reconciliation(...vals)).toBeCloseTo(expected, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property 4: calcChangeRate direction + zero guard', () => {
    expect(calcChangeRate(0, 100)).toBeNull()
    fc.assert(fc.property(
      fc.float({ min: Math.fround(-1e6), max: Math.fround(1e6), noNaN: true }),
      fc.float({ min: Math.fround(-1e6), max: Math.fround(1e6), noNaN: true }),
      (prior, cur) => {
        fc.pre(Math.abs(prior) > 1e-9)
        expect(calcChangeRate(prior, cur)).toBeCloseTo((cur - prior) / Math.abs(prior), 5)
      },
    ), { numRuns: 50 })
  })

  it('Property 5: isDebitCreditBalanced ↔ |SUM差|<0.01', () => {
    fc.assert(fc.property(fc.array(fc.float()), fc.array(fc.float()), (d, c) => {
      const ds = d.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0)
      const cs = c.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0)
      expect(isDebitCreditBalanced(d, c)).toBe(Math.abs(ds - cs) < 0.01)
    }), { numRuns: 50 })
  })

  it('Property 6: parseNum robustness', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(42)).toBe(42)
  })
})
