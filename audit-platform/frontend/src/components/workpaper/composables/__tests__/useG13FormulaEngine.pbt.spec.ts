/**
 * Property-Based Tests — G13 公允价值变动收益公式引擎
 *
 * Spec: .kiro/specs/g13-fair-value-changes/ Tasks 2.2 ~ 2.7
 * 覆盖 Property 1~6
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcAdjustedAmount,
  calcFVChange,
  calcChangeRate,
  isDebitCreditBalanced,
  isFvReconciled,
  calcVariance,
} from '../useG13FormulaEngine'

const dbl = (min: number, max: number) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

describe('Feature: g13-fair-value-changes, Property 1: 审定数=未审数+调整数', () => {
  it('calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), (unadjusted, adjustment) => {
        expect(calcAdjustedAmount(unadjusted, adjustment)).toBeCloseTo(unadjusted + adjustment, 5)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g13-fair-value-changes, Property 2: FV变动=期末-期初', () => {
  it('calcFVChange(opening, closing) === closing - opening', () => {
    fc.assert(
      fc.property(dbl(-1e9, 1e9), dbl(-1e9, 1e9), (opening, closing) => {
        expect(calcFVChange(opening, closing)).toBeCloseTo(closing - opening, 5)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g13-fair-value-changes, Property 3: FV变动=审定数时差异为零', () => {
  it('calcVariance === 0 when fvChange equals adjusted', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), (unadjusted, adjustment) => {
        const audited = calcAdjustedAmount(unadjusted, adjustment)
        const fvChange = audited
        expect(calcVariance(fvChange, audited)).toBeCloseTo(0, 5)
        expect(isFvReconciled(fvChange, audited)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g13-fair-value-changes, Property 4: 变动率方向正确+除零→null', () => {
  it('direction and zero guard', () => {
    fc.assert(
      fc.property(fc.double({ min: 0.01, max: 1e8, noNaN: true }), dbl(-1e8, 1e8), (prior, current) => {
        const rate = calcChangeRate(prior, current)
        expect(rate).not.toBeNull()
        if (current > prior) expect(rate!).toBeGreaterThan(0)
        if (current < prior) expect(rate!).toBeLessThan(0)
      }),
      { numRuns: 100 },
    )
    expect(calcChangeRate(0, 100)).toBeNull()
  })
})

describe('Feature: g13-fair-value-changes, Property 5: 借贷平衡', () => {
  it('isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true }), { minLength: 1, maxLength: 20 }),
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true }), { minLength: 1, maxLength: 20 }),
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

describe('Feature: g13-fair-value-changes, Property 6: parseNum健壮性', () => {
  it('invalid → 0; finite → value', () => {
    for (const v of [null, undefined, '', NaN, 'abc']) {
      expect(parseNum(v)).toBe(0)
    }
    fc.assert(
      fc.property(dbl(-1e8, 1e8), (n) => {
        expect(parseNum(n)).toBeCloseTo(n, 5)
      }),
      { numRuns: 100 },
    )
  })
})
