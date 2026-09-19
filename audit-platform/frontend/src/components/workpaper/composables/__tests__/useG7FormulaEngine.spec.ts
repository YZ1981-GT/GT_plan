/**
 * Property-Based Tests — G7 长期股权投资(main组) 公式引擎
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Tasks 1.2 ~ 1.9
 * 8个PBT属性覆盖8纯函数+parseNum
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcEndingCost,
  calcEndingEquityAdj,
  calcBookValue,
  calcChangeRate,
  isDebitCreditBalanced,
} from '../useG7FormulaEngine'

// ═══════════════════════════════════════════════════════════════════
// P1: 借方余额公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 1: 借方余额公式', () => {
  /**
   * **Validates: Requirements 3.3, 6.2**
   */
  it('calcDebitBalance(opening, debit, credit) === opening + debit - credit', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (opening, debit, credit) => {
          expect(calcDebitBalance(opening, debit, credit)).toBeCloseTo(opening + debit - credit, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P2: 审定数公式（三参数）
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 2: 审定数公式', () => {
  /**
   * **Validates: Requirements 3.3, 6.2**
   */
  it('calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (unadjusted, aje, rje) => {
          expect(calcAdjustedAmount(unadjusted, aje, rje)).toBeCloseTo(unadjusted + aje + rje, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P3: 期末投资成本公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 3: 期末投资成本公式', () => {
  /**
   * **Validates: Requirements 5.3, 6.2**
   */
  it('calcEndingCost(opening, increase, decrease) === opening + increase - decrease', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (opening, increase, decrease) => {
          expect(calcEndingCost(opening, increase, decrease)).toBeCloseTo(opening + increase - decrease, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P4: 期末权益法调整公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 4: 期末权益法调整公式', () => {
  /**
   * **Validates: Requirements 5.4, 6.2**
   */
  it('calcEndingEquityAdj(opening, equityIncrease, equityDecrease) === opening + equityIncrease - equityDecrease', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (opening, equityIncrease, equityDecrease) => {
          expect(calcEndingEquityAdj(opening, equityIncrease, equityDecrease)).toBeCloseTo(
            opening + equityIncrease - equityDecrease,
            5,
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P5: 账面价值公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 5: 账面价值公式', () => {
  /**
   * **Validates: Requirements 5.5, 6.2**
   */
  it('calcBookValue(subtotal, impairment) === subtotal - impairment', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (subtotal, impairment) => {
          expect(calcBookValue(subtotal, impairment)).toBeCloseTo(subtotal - impairment, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P6: 变动率方向性与除零保护
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 6: 变动率方向性与除零保护', () => {
  /**
   * **Validates: Requirements 3.5, 6.2**
   */
  it('current > prior > 0 → positive rate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (prior, delta) => {
          const current = prior + delta
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          expect(result!).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('current < prior, prior > 0 → negative rate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.02, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (prior, delta) => {
          const current = prior - Math.min(delta, prior * 0.99)
          if (current >= prior) return // skip degenerate
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          expect(result!).toBeLessThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcChangeRate(0, any) === null', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (current) => {
          expect(calcChangeRate(0, current)).toBeNull()
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P7: 借贷平衡恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 7: 借贷平衡恒等', () => {
  /**
   * **Validates: Requirements 6.1, 6.2**
   */
  it('isDebitCreditBalanced(debits, credits) ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
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

// ═══════════════════════════════════════════════════════════════════
// P8: parseNum健壮性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g7-long-term-equity-main, Property 8: parseNum健壮性', () => {
  /**
   * **Validates: Requirements 6.2**
   */
  it('parseNum(null/undefined/empty/NaN) === 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum('  ')).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('parseNum(finite number) === number (property)', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (n) => {
          const expected = Object.is(n, -0) ? 0 : n
          expect(parseNum(n)).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('parseNum(numeric string) === parsed number (property)', () => {
    fc.assert(
      fc.property(
        fc.double({ noNaN: true, noDefaultInfinity: true }),
        (n) => {
          const expected = Object.is(n, -0) ? 0 : n
          expect(parseNum(String(n))).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})
