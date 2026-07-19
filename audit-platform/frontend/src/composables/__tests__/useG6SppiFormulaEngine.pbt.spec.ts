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
 * - P4: 盘点倒轧 = 盘点日数量 − 净增加（整数）
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
  calcInventoryRollForwardByDirection,
  calcFairValueDiff,
  calcFairValueAmount,
  calcFairValueQtyImpact,
  calcFairValuePriceImpact,
  resolveRollForwardDirection,
  migrateLegacyChangeToNetIncrease,
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

  it('calcEffectiveInterest(..., ACT/360) === round(cost * rate * days / 360, 2)', () => {
    fc.assert(
      fc.property(
        amounts(),
        rates(),
        days(),
        (cost, rate, d) => {
          expect(calcEffectiveInterest(cost, rate, d, 'ACT/360')).toBe(round2(cost * rate * d / 360))
        },
      ),
      { numRuns: 50 },
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

  it('calcCashInflow(..., ACT/360) === round(face * coupon * days / 360, 2)', () => {
    fc.assert(
      fc.property(
        amounts(),
        rates(),
        days(),
        (face, coupon, d) => {
          expect(calcCashInflow(face, coupon, d, 'ACT/360')).toBe(round2(face * coupon * d / 360))
        },
      ),
      { numRuns: 50 },
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
// P4: 盘点倒轧减法恒等
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-sppi, Property 4: 盘点倒轧减法恒等', () => {
  /**
   * **Validates: Requirements 6.3**
   * 报表日 = 盘点日 − 净增加（资产负债表日→盘点日）
   */
  it('calcInventoryRollForward(count, netIncrease) === count - netIncrease (integer)', () => {
    fc.assert(
      fc.property(
        quantities(),
        fc.integer({ min: -10000, max: 10000 }),
        (count, change) => {
          expect(calcInventoryRollForward(count, change)).toBe(count - change)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcInventoryRollForward(count, increase, decrease) === count - increase + decrease', () => {
    fc.assert(
      fc.property(
        quantities(),
        fc.integer({ min: 0, max: 5000 }),
        fc.integer({ min: 0, max: 5000 }),
        (count, increase, decrease) => {
          expect(calcInventoryRollForward(count, increase, decrease)).toBe(count - increase + decrease)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('方向：期后倒推 / 期前顺推 / 同日', () => {
    expect(resolveRollForwardDirection('2025-01-10', '2024-12-31')).toBe('backward')
    expect(resolveRollForwardDirection('2024-12-20', '2024-12-31')).toBe('forward')
    expect(resolveRollForwardDirection('2024-12-31', '2024-12-31')).toBe('sameDay')
    expect(resolveRollForwardDirection('', '2024-12-31')).toBe('unknown')
    expect(calcInventoryRollForwardByDirection(1000, 100, 'backward')).toBe(900)
    expect(calcInventoryRollForwardByDirection(1000, 100, 'forward')).toBe(1100)
    expect(calcInventoryRollForwardByDirection(1000, 100, 'sameDay')).toBe(1000)
    expect(migrateLegacyChangeToNetIncrease(-50)).toBe(50)
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

  it('calcFairValueAmount(qty, price) === round(qty × price, 2)', () => {
    fc.assert(
      fc.property(
        quantities(),
        amounts(),
        (qty, price) => {
          expect(calcFairValueAmount(qty, price)).toBe(round2(qty * price))
        },
      ),
      { numRuns: 100 },
    )
  })

  it('数量影响 + 价格影响 ≈ 总差异（分量各自四舍五入，允许 ±0.02）', () => {
    // 价格用「分」整数再 /100，贴近财务金额
    const prices = () => fc.integer({ min: 1, max: 1_000_000 }).map(cents => cents / 100)
    fc.assert(
      fc.property(
        quantities(),
        quantities(),
        prices(),
        prices(),
        (unadjQty, auditedQty, unadjPrice, auditedPrice) => {
          const unadjFv = calcFairValueAmount(unadjQty, unadjPrice)
          const auditedFv = calcFairValueAmount(auditedQty, auditedPrice)
          const diff = calcFairValueDiff(auditedFv, unadjFv)
          const qtyImpact = calcFairValueQtyImpact(auditedQty, unadjQty, unadjPrice)
          const priceImpact = calcFairValuePriceImpact(auditedQty, auditedPrice, unadjPrice)
          expect(Math.abs(round2(qtyImpact + priceImpact) - diff)).toBeLessThanOrEqual(0.02)
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
