/**
 * Property-Based Tests — G12 净敞口套期收益公式引擎
 *
 * Spec: .kiro/specs/g12-net-hedge-gains/ Tasks 1.2 ~ 1.8
 * 覆盖 Property 1~7
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcAdjustedAmount,
  calcFVChange,
  calcChangeRate,
  calcHedgeIneffectiveness,
  isDebitCreditBalanced,
} from '../useG12FormulaEngine'

const dbl = (min: number, max: number) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

describe('Feature: g12-net-hedge-gains, Property 1: 审定数=未审数+调整数', () => {
  it('calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), (unadjusted, adjustment) => {
        expect(calcAdjustedAmount(unadjusted, adjustment)).toBeCloseTo(unadjusted + adjustment, 5)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g12-net-hedge-gains, Property 2: FV变动=期末-期初', () => {
  it('calcFVChange(opening, closing) === closing - opening', () => {
    fc.assert(
      fc.property(dbl(-1e9, 1e9), dbl(-1e9, 1e9), (opening, closing) => {
        expect(calcFVChange(opening, closing)).toBeCloseTo(closing - opening, 5)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g12-net-hedge-gains, Property 3: 套期无效部分绝对差', () => {
  it('calcHedgeIneffectiveness === |instrumentChange - itemChange|', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), (instrumentChange, itemChange) => {
        expect(calcHedgeIneffectiveness(instrumentChange, itemChange)).toBeCloseTo(
          Math.abs(instrumentChange - itemChange),
          5,
        )
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g12-net-hedge-gains, Property 4: 套期无效部分非负性', () => {
  it('calcHedgeIneffectiveness >= 0', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), (instrumentChange, itemChange) => {
        expect(calcHedgeIneffectiveness(instrumentChange, itemChange)).toBeGreaterThanOrEqual(0)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g12-net-hedge-gains, Property 5: 变动率除零保护', () => {
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

describe('Feature: g12-net-hedge-gains, Property 6: 借贷平衡', () => {
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

describe('Feature: g12-net-hedge-gains, Property 7: parseNum健壮性', () => {
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
