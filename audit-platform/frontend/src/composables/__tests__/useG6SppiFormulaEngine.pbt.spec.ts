/**
 * Property-Based Tests — G6 其他债权投资(SPPI组) 公式引擎
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Tasks 1.2 ~ 1.7
 * Framework: vitest + fast-check, numRuns ≥ 100
 *
 * 6 Properties:
 * - P1: 实际利息收入 = amortizedCost × effectiveRate × days / 365（2dp）
 * - P2: 现金流入 = faceValue × couponRate × days / 365（2dp）
 * - P3: 期末摊余成本 = opening + interest - cashInflow（2dp）
 * - P4: 盘点倒轧 = 盘点日数量 + 增减（整数）
 * - P5: 公允价值差异 = audited - unadjusted（2dp）
 * - P6: parseNum健壮性 — null/undefined/''/NaN → 0; finite n → n
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcEffectiveInterest,
  calcCashInflow,
  calcEndingAmortized,
  calcInventoryRollForward,
  calcFairValueDiff,
} from '../useG6SppiFormulaEngine'

// ═══ Generators ═══
const amounts = () => fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true })
const rates = () => fc.float({ min: 0, max: Math.fround(0.3), noNaN: true, noDefaultInfinity: true })
const days = () => fc.integer({ min: 1, max: 365 })
const quantities = () => fc.integer({ min: 0, max: 1000000 })

// ═══ Helper: round to 2 decimal places ═══
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══════════════════════════════════════════════════════════════════
// P1: 实际利息收入公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-sppi, Property 1: 实际利息收入公式', () => {
  /**
   * **Validates: Requirements 3.2**
   */
  it('calcEffectiveInterest(cost, rate, days) === round(cost * rate * days / 365, 2)', () => {
    fc.assert(
      fc.property(
        amounts(),
        rates(),
        days(),
        (cost, rate, d) => {
          expect(calcEffectiveInterest(cost, rate, d)).toBe(round2(cost * rate * d / 365))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P2: 现金流入公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-sppi, Property 2: 现金流入公式', () => {
  /**
   * **Validates: Requirements 3.3**
   */
  it('calcCashInflow(face, coupon, days) === round(face * coupon * days / 365, 2)', () => {
    fc.assert(
      fc.property(
        amounts(),
        rates(),
        days(),
        (face, coupon, d) => {
          expect(calcCashInflow(face, coupon, d)).toBe(round2(face * coupon * d / 365))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P3: 期末摊余成本恒等式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-sppi, Property 3: 期末摊余成本恒等式', () => {
  /**
   * **Validates: Requirements 3.4**
   */
  it('calcEndingAmortized(open, interest, cash) === round(open + interest - cash, 2)', () => {
    fc.assert(
      fc.property(
        amounts(),
        amounts(),
        amounts(),
        (open, interest, cash) => {
          expect(calcEndingAmortized(open, interest, cash)).toBe(round2(open + interest - cash))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P4: 盘点倒轧加法恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-sppi, Property 4: 盘点倒轧加法恒等', () => {
  /**
   * **Validates: Requirements 6.3**
   */
  it('calcInventoryRollForward(count, change) === count + change (integer)', () => {
    fc.assert(
      fc.property(
        quantities(),
        fc.integer({ min: -10000, max: 10000 }),
        (count, change) => {
          expect(calcInventoryRollForward(count, change)).toBe(count + change)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P5: 公允价值差异公式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-sppi, Property 5: 公允价值差异公式', () => {
  /**
   * **Validates: Requirements 2.2, 7.1**
   */
  it('calcFairValueDiff(audited, unadjusted) === round(audited - unadjusted, 2)', () => {
    fc.assert(
      fc.property(
        amounts(),
        amounts(),
        (audited, unadjusted) => {
          expect(calcFairValueDiff(audited, unadjusted)).toBe(round2(audited - unadjusted))
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// P6: parseNum健壮性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-sppi, Property 6: parseNum健壮性', () => {
  /**
   * **Validates: Requirements 7.1**
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
