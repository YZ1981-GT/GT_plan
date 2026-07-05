import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcAdjustedAmount,
  calcAverageBalance,
  calcReturnRate,
  calcChangeRate,
  isDebitCreditBalanced,
} from '../useG11FormulaEngine'

describe('useG11FormulaEngine', () => {
  it('Property 1: calcAdjustedAmount', () => {
    fc.assert(fc.property(fc.float(), fc.float(), (u, a) => {
      const uu = Number.isFinite(u) ? u : 0
      const aa = Number.isFinite(a) ? a : 0
      expect(calcAdjustedAmount(uu, aa)).toBeCloseTo(uu + aa, 5)
    }), { numRuns: 50 })
  })

  it('Property 2: calcAverageBalance', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, noNaN: true }),
      fc.float({ min: 0, noNaN: true }),
      (o, c) => {
        expect(calcAverageBalance(o, c)).toBeCloseTo((o + c) / 2, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property 3-4: calcReturnRate', () => {
    expect(calcReturnRate(100, 0)).toBeNull()
    fc.assert(fc.property(
      fc.float({ noNaN: true }),
      fc.float({ min: Math.fround(0.01), max: 1e6, noNaN: true }),
      (income, bal) => {
        expect(calcReturnRate(income, bal)).toBeCloseTo(income / bal, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property 5: calcChangeRate', () => {
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

  it('Property 6: isDebitCreditBalanced', () => {
    fc.assert(fc.property(fc.array(fc.float()), fc.array(fc.float()), (d, c) => {
      const ds = d.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0)
      const cs = c.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0)
      expect(isDebitCreditBalanced(d, c)).toBe(Math.abs(ds - cs) < 0.01)
    }), { numRuns: 50 })
  })

  it('Property 7: parseNum', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(42)).toBe(42)
  })
})
