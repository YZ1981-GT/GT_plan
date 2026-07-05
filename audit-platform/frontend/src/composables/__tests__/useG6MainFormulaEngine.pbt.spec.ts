/**
 * Property-Based Tests — G6 其他债权投资(main组) 公式引擎
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Tasks 1.2 ~ 1.9
 * Framework: vitest + fast-check, numRuns ≥ 100
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcSubtotal,
  calcEndingSubtotal,
  calcUnadjustedProvision,
  calcImpairmentAdjustment,
  calcAdjustedBookValue,
  calcChangeRate,
  isDebitCreditBalanced,
} from '../useG6MainFormulaEngine'

// ═══ Generators ═══
const amount = () => fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
const positiveAmount = () => fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })
const rate = () => fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true })
const amountArray = () => fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 0, maxLength: 50 })

// ═══ Helper: round to 2 decimal places ═══
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══════════════════════════════════════════════════════════════════
// P1: 借方余额公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 1: 借方余额公式', () => {
  /**
   * **Validates: Requirements 3.3, 7.2**
   */
  it('calcDebitBalance(o, d, c) === round(o + d - c, 2) for all amounts', () => {
    fc.assert(
      fc.property(
        amount(),
        positiveAmount(),
        positiveAmount(),
        (opening, debit, credit) => {
          expect(calcDebitBalance(opening, debit, credit)).toBe(round2(opening + debit - credit))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P2: 审定数公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 2: 审定数公式', () => {
  /**
   * **Validates: Requirements 3.3, 7.2**
   */
  it('calcAdjustedAmount(u, a) === round(u + a, 2) for all amounts', () => {
    fc.assert(
      fc.property(
        amount(),
        amount(),
        (unadjusted, adjustment) => {
          expect(calcAdjustedAmount(unadjusted, adjustment)).toBe(round2(unadjusted + adjustment))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P3: 余额小计(三要素加法)
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 3: 余额小计(三要素加法)', () => {
  /**
   * **Validates: Requirements 3.1, 5.1, 7.2**
   */
  it('calcSubtotal(cost, intAdj, accInt) === round(cost + intAdj + accInt, 2)', () => {
    fc.assert(
      fc.property(
        amount(),
        amount(),
        amount(),
        (cost, intAdj, accruedInterest) => {
          expect(calcSubtotal(cost, intAdj, accruedInterest)).toBe(round2(cost + intAdj + accruedInterest))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P4: 期末小计公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 4: 期末小计公式', () => {
  /**
   * **Validates: Requirements 5.2**
   */
  it('calcEndingSubtotal(open, inc, dec, int) === round(open + inc - dec + int, 2)', () => {
    fc.assert(
      fc.property(
        amount(),
        positiveAmount(),
        positiveAmount(),
        positiveAmount(),
        (openingSubtotal, increase, decrease, interestIncome) => {
          expect(calcEndingSubtotal(openingSubtotal, increase, decrease, interestIncome))
            .toBe(round2(openingSubtotal + increase - decrease + interestIncome))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P5: ECL公式链一致性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 5: ECL公式链一致性', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * ECL恒等式验证：
   * ③ = ① × ②
   * ⑥ = ⑤×②A + ①×(②A-②)
   * ⑦ = ① + ⑤
   * ⑧ = ③ + ⑥ = ⑦ × ②A
   * ⑨ = ⑦ - ⑧ = ⑦ × (1-②A)
   */
  it('⑧ = ③ + ⑥ === ⑦ × ②A (恒等式验证)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e8), noNaN: true, noDefaultInfinity: true }),       // ① 账面余额
        fc.float({ min: Math.fround(0.01), max: Math.fround(0.99), noNaN: true, noDefaultInfinity: true }),   // ② 损失率
        fc.float({ min: Math.fround(-1e7), max: Math.fround(1e7), noNaN: true, noDefaultInfinity: true }),    // ⑤ 余额调整
        fc.float({ min: Math.fround(0.01), max: Math.fround(0.99), noNaN: true, noDefaultInfinity: true }),   // ②A 调整后损失率
        (bal, rateOrig, adj, adjRate) => {
          const prov = calcUnadjustedProvision(bal, rateOrig)                           // ③
          const impAdj = calcImpairmentAdjustment(adj, adjRate, bal, rateOrig)          // ⑥
          const adjBal = bal + adj                                                      // ⑦
          const adjProv = prov + impAdj                                                 // ⑧ = ③ + ⑥

          // 恒等式：⑧ should equal ⑦ × ②A
          const expected = adjBal * adjRate

          // Allow for intermediate rounding differences (each step rounds to 2dp)
          expect(Math.abs(adjProv - expected)).toBeLessThanOrEqual(0.02)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('⑨ = calcAdjustedBookValue(⑦, ⑧) === ⑦ × (1-②A) (审定账面价值)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e8), noNaN: true, noDefaultInfinity: true }),       // ① 账面余额
        fc.float({ min: Math.fround(0.01), max: Math.fround(0.99), noNaN: true, noDefaultInfinity: true }),   // ② 损失率
        fc.float({ min: Math.fround(-1e7), max: Math.fround(1e7), noNaN: true, noDefaultInfinity: true }),    // ⑤ 余额调整
        fc.float({ min: Math.fround(0.01), max: Math.fround(0.99), noNaN: true, noDefaultInfinity: true }),   // ②A 调整后损失率
        (bal, rateOrig, adj, adjRate) => {
          const prov = calcUnadjustedProvision(bal, rateOrig)                           // ③
          const impAdj = calcImpairmentAdjustment(adj, adjRate, bal, rateOrig)          // ⑥
          const adjBal = bal + adj                                                      // ⑦
          const adjProv = prov + impAdj                                                 // ⑧
          const bookValue = calcAdjustedBookValue(adjBal, adjProv)                      // ⑨

          // ⑨ should equal ⑦(1-②A)
          const expected = adjBal * (1 - adjRate)

          // Allow for rounding accumulation
          expect(Math.abs(bookValue - expected)).toBeLessThanOrEqual(0.03)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P6: 变动率方向性与除零保护
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 6: 变动率方向性与除零保护', () => {
  /**
   * **Validates: Requirements 3.5, 7.2**
   */
  it('calcChangeRate(0, any) === null (除零保护)', () => {
    fc.assert(
      fc.property(
        amount(),
        (current) => {
          expect(calcChangeRate(0, current)).toBeNull()
        },
      ),
      { numRuns: 100 },
    )
  })

  it('current > prior > 0 → rate >= 0 (非负方向，4dp精度)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: Math.fround(1), max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }),
        (prior, delta) => {
          const current = prior + delta // current > prior guaranteed
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          // Due to 4dp rounding, very small deltas relative to prior can round to 0
          expect(result!).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('significant increase → rate strictly > 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e4), noNaN: true, noDefaultInfinity: true }),
        (prior) => {
          // Ensure delta is large enough to survive 4dp rounding: delta/prior > 0.00005
          const current = prior * 2 // 100% increase always produces rate > 0
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          expect(result!).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('current < prior, prior > 0 → rate <= 0 (非正方向，4dp精度)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: Math.fround(1), max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }),
        (prior, delta) => {
          const current = prior - delta
          if (current < prior) {
            const result = calcChangeRate(prior, current)
            expect(result).not.toBeNull()
            // Due to 4dp rounding, very small decreases relative to prior can round to 0
            expect(result!).toBeLessThanOrEqual(0)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('significant decrease → rate strictly < 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(2), max: Math.fround(1e4), noNaN: true, noDefaultInfinity: true }),
        (prior) => {
          // 50% decrease always produces rate < 0
          const current = prior / 2
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          expect(result!).toBeLessThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P7: 借贷平衡恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 7: 借贷平衡恒等', () => {
  /**
   * **Validates: Requirements 7.1, 7.2**
   */
  it('isDebitCreditBalanced(d, c) ↔ |SUM(d)-SUM(c)| < 0.01', () => {
    fc.assert(
      fc.property(
        amountArray(),
        amountArray(),
        (d, c) => {
          const sumD = d.reduce((s, v) => s + v, 0)
          const sumC = c.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(d, c)).toBe(Math.abs(sumD - sumC) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P8: parseNum健壮性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-main, Property 8: parseNum健壮性', () => {
  /**
   * **Validates: Requirements 7.2**
   */
  it('parseNum(null/undefined/\'\'/NaN) === 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum('  ')).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('∀ finite n: parseNum(n) === n', () => {
    fc.assert(
      fc.property(
        fc.float({ noNaN: true, noDefaultInfinity: true }),
        (n) => {
          expect(parseNum(n)).toBe(n)
        },
      ),
      { numRuns: 100 },
    )
  })
})
