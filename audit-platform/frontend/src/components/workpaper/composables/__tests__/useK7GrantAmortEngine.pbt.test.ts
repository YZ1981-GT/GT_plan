/**
 * K7 递延收益 — Property-Based Testing (CP-K7-03, CP-K7-04, CP-K7-05)
 *
 * 覆盖 useK7GrantAmortEngine 全部纯函数。
 * 使用 fast-check 验证数学正确性。
 *
 * Spec: .kiro/specs/k7-deferred-income/design.md → Correctness Properties CP-K7-03~05
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcStraightLineAmort,
  calcRemainingBalance,
  calcAmortVariance,
} from '../useK7GrantAmortEngine'

describe('useK7GrantAmortEngine PBT', () => {
  // 安全浮点生成器
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // ═══ CP-K7-03: 直线分摊 ═══
  // **Validates: Requirements 7.3**
  it('Property CP-K7-03: calcStraightLineAmort(t, tp, cp) ≈ (t / tp) * cp', () => {
    // 生成器约束：total≥0, totalPeriods>0, currentPeriods≥0
    const totalArb = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: 0,
      max: Math.fround(1e9),
    })
    const totalPeriodsArb = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: Math.fround(0.001),
      max: Math.fround(1e6),
    })
    const currentPeriodsArb = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: 0,
      max: Math.fround(1e6),
    })

    fc.assert(
      fc.property(totalArb, totalPeriodsArb, currentPeriodsArb, (t, tp, cp) => {
        fc.pre(tp > 0)
        const actual = calcStraightLineAmort(t, tp, cp)
        const expected = (t / tp) * cp
        if (Math.abs(expected) < 1e-9) {
          expect(actual).toBeCloseTo(expected, 4)
        } else {
          expect(Math.abs(actual - expected) / Math.abs(expected)).toBeLessThan(1e-6)
        }
      }),
      { numRuns: 200 },
    )
  })

  // ═══ CP-K7-04: 期末余额 ═══
  // **Validates: Requirements 7.4**
  it('Property CP-K7-04: calcRemainingBalance(total, acc) === max(0, total - acc)', () => {
    const posFloat = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: 0,
      max: Math.fround(1e9),
    })

    fc.assert(
      fc.property(posFloat, posFloat, (total, acc) => {
        const actual = calcRemainingBalance(total, acc)
        const expected = Math.max(0, total - acc)
        expect(actual).toBeCloseTo(expected, 5)
      }),
      { numRuns: 200 },
    )
  })

  // ═══ CP-K7-05: 分摊差异 ═══
  // **Validates: Requirements 7.5**
  it('Property CP-K7-05: calcAmortVariance(calc, booked) === calc - booked', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, (calc, booked) => {
        expect(calcAmortVariance(calc, booked)).toBeCloseTo(calc - booked, 5)
      }),
      { numRuns: 200 },
    )
  })
})
