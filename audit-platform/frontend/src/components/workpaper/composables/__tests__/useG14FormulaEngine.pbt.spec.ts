/**
 * Property-Based Tests — G14 信用减值损失公式引擎
 *
 * Spec: .kiro/specs/g14-credit-impairment-loss/ Tasks 2.2 ~ 2.8
 * 覆盖 Property 1~7
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcAdjustedAmount,
  calcNetImpairmentLoss,
  calcProvisionRollForward,
  calcChangeRate,
  isDebitCreditBalanced,
  isRollForwardBalanced,
  isReconciled,
  calcVariance,
} from '../useG14FormulaEngine'

const dbl = (min: number, max: number) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const nonNeg = (min: number, max: number) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

// Property 1: 审定数公式
describe('Feature: g14-credit-impairment-loss, Property 1: 审定数=未审数+调整数', () => {
  it('calcAdjustedAmount(unadjusted, adjustment) === unadjusted + adjustment', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), (unadjusted, adjustment) => {
        expect(calcAdjustedAmount(unadjusted, adjustment)).toBeCloseTo(unadjusted + adjustment, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// Property 2: 净信用减值损失
describe('Feature: g14-credit-impairment-loss, Property 2: 净信用减值损失=计提-转回', () => {
  it('calcNetImpairmentLoss(provision, reversal) === provision - reversal', () => {
    fc.assert(
      fc.property(nonNeg(0, 1e8), nonNeg(0, 1e8), (provision, reversal) => {
        expect(calcNetImpairmentLoss(provision, reversal)).toBeCloseTo(provision - reversal, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// Property 3: 坏账准备滚动恒等（转回正数）
describe('Feature: g14-credit-impairment-loss, Property 3: 坏账准备滚动=期初+计提-转回-转销+其他', () => {
  it('calcProvisionRollForward === opening + provision - reversal - writeoff + other', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), nonNeg(0, 1e8), nonNeg(0, 1e8), dbl(-1e8, 1e8),
        (opening, provision, reversal, writeoff, other) => {
          expect(calcProvisionRollForward(opening, provision, reversal, writeoff, other)).toBeCloseTo(
            opening + provision - reversal - writeoff + other,
            5,
          )
        }),
      { numRuns: 100 },
    )
  })
})

// Property 4: 坏账准备滚动验证检测
describe('Feature: g14-credit-impairment-loss, Property 4: 坏账准备滚动验证检测', () => {
  it('balanced when computed matches actual within tolerance', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), nonNeg(0, 1e8), nonNeg(0, 1e8), dbl(-1e8, 1e8), (opening, provision, reversal, writeoff, other) => {
        const closing = calcProvisionRollForward(opening, provision, reversal, writeoff, other)
        expect(isRollForwardBalanced(opening, provision, reversal, writeoff, closing, other)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })

  it('unbalanced when actual differs by more than tolerance', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), nonNeg(0, 1e8), nonNeg(0, 1e8), dbl(-1e8, 1e8), (opening, provision, reversal, writeoff, other) => {
        const closing = calcProvisionRollForward(opening, provision, reversal, writeoff, other) + 1
        expect(isRollForwardBalanced(opening, provision, reversal, writeoff, closing, other)).toBe(false)
      }),
      { numRuns: 100 },
    )
  })
})

// Property 5: 变动率方向性与除零保护
describe('Feature: g14-credit-impairment-loss, Property 5: 变动率方向正确+除零→null', () => {
  it('current > prior → rate > 0', () => {
    fc.assert(
      fc.property(dbl(0.01, 1e8), dbl(0.01, 1e8), (prior, delta) => {
        const current = prior + delta
        const rate = calcChangeRate(prior, current)
        expect(rate).not.toBeNull()
        expect(rate!).toBeGreaterThan(0)
      }),
      { numRuns: 100 },
    )
  })

  it('current < prior → rate < 0', () => {
    fc.assert(
      fc.property(dbl(0.01, 1e8), dbl(0.01, 1e8), (prior, delta) => {
        const current = prior - delta
        const rate = calcChangeRate(prior, current)
        expect(rate).not.toBeNull()
        expect(rate!).toBeLessThan(0)
      }),
      { numRuns: 100 },
    )
  })

  it('calcChangeRate(0, any) === null', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), (current) => {
        expect(calcChangeRate(0, current)).toBeNull()
      }),
      { numRuns: 100 },
    )
  })
})

// Property 6: 借贷平衡
describe('Feature: g14-credit-impairment-loss, Property 6: 借贷平衡', () => {
  it('isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(dbl(0, 1e6), { minLength: 1, maxLength: 20 }),
        fc.array(dbl(0, 1e6), { minLength: 1, maxLength: 20 }),
        (debits, credits) => {
          const dSum = debits.reduce((s, v) => s + v, 0)
          const cSum = credits.reduce((s, v) => s + v, 0)
          const balanced = isDebitCreditBalanced(debits, credits)
          expect(balanced).toBe(Math.abs(dSum - cSum) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// Property 7: parseNum健壮性
describe('Feature: g14-credit-impairment-loss, Property 7: parseNum健壮性', () => {
  it('无效输入→0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum('abc')).toBe(0)
  })

  it('有效finite数→原值', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), (n) => {
        expect(parseNum(n)).toBeCloseTo(n, 5)
      }),
      { numRuns: 100 },
    )
  })
})

describe('Feature: g14-credit-impairment-loss, calcVariance', () => {
  it('calcVariance(computed, actual) === computed - actual', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), (computed, actual) => {
        expect(calcVariance(computed, actual)).toBeCloseTo(computed - actual, 5)
      }),
      { numRuns: 50 },
    )
  })
})

describe('Feature: g14-credit-impairment-loss, isReconciled', () => {
  it('audited equals profitLoss within tolerance', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), (v) => {
        expect(isReconciled(v, v)).toBe(true)
        expect(isReconciled(v, v + 0.02)).toBe(false)
      }),
      { numRuns: 50 },
    )
  })
})
