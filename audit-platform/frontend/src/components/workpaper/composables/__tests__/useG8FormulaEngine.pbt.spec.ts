import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcEndingBalance,
  calcFairValueDiff,
  calcChangeRate,
  isDebitCreditBalanced,
} from '../useG8FormulaEngine'

const num = fc.float({ min: -1e6, max: 1e6, noNaN: true })

describe('G8 PBT — 公式引擎', () => {
  it('P1: calcDebitBalance === opening + debit - credit', () => {
    fc.assert(fc.property(num, num, num, (o, d, c) => {
      expect(calcDebitBalance(o, d, c)).toBeCloseTo(o + d - c, 4)
    }), { numRuns: 100 })
  })

  it('P2: calcAdjustedAmount === unadjusted + adjustment', () => {
    fc.assert(fc.property(num, num, (u, a) => {
      expect(calcAdjustedAmount(u, a)).toBeCloseTo(u + a, 4)
    }), { numRuns: 100 })
  })

  it('P3: calcEndingBalance 4 因子', () => {
    fc.assert(fc.property(num, num, num, num,
      (o, inc, dec, fv) => {
        expect(calcEndingBalance(o, inc, dec, fv))
          .toBeCloseTo(o + inc - dec + fv, 3)
      }), { numRuns: 100 })
  })

  it('P4: calcFairValueDiff === audited - unadjusted', () => {
    fc.assert(fc.property(num, num, (a, u) => {
      expect(calcFairValueDiff(a, u)).toBeCloseTo(a - u, 4)
    }), { numRuns: 100 })
  })

  it('P5: calcChangeRate 除零保护', () => {
    expect(calcChangeRate(0, 100)).toBeNull()
    expect(calcChangeRate(100, 150)).toBeCloseTo(0.5, 4)
    expect(calcChangeRate(100, 50)).toBeCloseTo(-0.5, 4)
  })

  it('P6: 借贷平衡', () => {
    fc.assert(fc.property(
      fc.array(num, { minLength: 1, maxLength: 8 }),
      fc.array(num, { minLength: 1, maxLength: 8 }),
      (debits, credits) => {
        const d = debits.reduce((s, v) => s + v, 0)
        const c = credits.reduce((s, v) => s + v, 0)
        expect(isDebitCreditBalanced(debits, credits)).toBe(Math.abs(d - c) < 0.01)
      },
    ), { numRuns: 50 })
  })

  it('P7: parseNum 健壮性', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('  ')).toBe(0)
    expect(parseNum('abc')).toBe(0)
  })

  it('P8: 期末余额与审定一致性', () => {
    fc.assert(fc.property(num, num, num, num, num,
      (openingAdj, inc, dec, fv, adj) => {
        const ending = calcEndingBalance(openingAdj, inc, dec, fv)
        expect(calcAdjustedAmount(ending, adj))
          .toBeCloseTo(openingAdj + inc - dec + fv + adj, 3)
      }), { numRuns: 50 })
  })
})
