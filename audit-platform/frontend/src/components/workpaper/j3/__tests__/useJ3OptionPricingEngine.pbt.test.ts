/**
 * J3 股份支付 — Black-Scholes 期权定价 + 费用分摊 Property-Based Tests (CP-J3-01~06)
 *
 * 覆盖 useJ3OptionPricingEngine + useJ3FormulaEngine 全部纯函数。
 * 使用 fast-check 验证数学正确性。
 *
 * Spec: .kiro/specs/j3-share-based-payment/design.md → Correctness Properties CP-J3-01~06
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcBlackScholes,
  calcD1,
  calcD2,
  normalCDF,
} from '../../../../composables/workpaper/j3/useJ3OptionPricingEngine'
import {
  calcCumulativeExpense,
  calcRemainingExpense,
  calcTotalFairValue,
  calcSubtotal,
} from '../../../../composables/workpaper/j3/useJ3FormulaEngine'

fc.configureGlobal({ numRuns: 200 })

const EPSILON = 1e-6

// 安全浮点生成器（Math.fround确保32位）
const safeFloat = (min = -1e6, max = 1e6) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

// ═══ CP-J3-01: Black-Scholes定价公式 ═══
// **Validates: Requirements 3.1**
describe('Feature: j3-share-based-payment, Property CP-J3-01: Black-Scholes定价公式', () => {
  it('CP-J3-01: calcBlackScholes(S,K,T,r,σ) === S×N(d1) - K×exp(-r×T)×N(d2)', () => {
    fc.assert(
      fc.property(
        safeFloat(1, 1000),     // S: 标的价格
        safeFloat(1, 1000),     // K: 行权价
        safeFloat(0.1, 10),     // T: 到期时间(年)
        safeFloat(0.01, 0.10),  // r: 无风险利率
        safeFloat(0.1, 1.0),    // sigma: 波动率
        (S, K, T, r, sigma) => {
          const result = calcBlackScholes(S, K, T, r, sigma)
          // 重新计算验证
          const d1 = calcD1(S, K, T, r, sigma)
          const d2 = calcD2(d1, sigma, T)
          const expected = S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2)
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        },
      ),
    )
  })

  it('CP-J3-01b: BS价格 >= 0（非负性）', () => {
    fc.assert(
      fc.property(
        safeFloat(1, 1000),
        safeFloat(1, 1000),
        safeFloat(0.1, 10),
        safeFloat(0.01, 0.10),
        safeFloat(0.1, 1.0),
        (S, K, T, r, sigma) => {
          const result = calcBlackScholes(S, K, T, r, sigma)
          expect(result).toBeGreaterThanOrEqual(-EPSILON)
        },
      ),
    )
  })
})

// ═══ CP-J3-02: d2=d1-σ×√T ═══
// **Validates: Requirements 3.3**
describe('Feature: j3-share-based-payment, Property CP-J3-02: d2公式', () => {
  it('CP-J3-02: calcD2(d1, sigma, T) === d1 - sigma × Math.sqrt(T)', () => {
    fc.assert(
      fc.property(
        safeFloat(-10, 10),    // d1
        safeFloat(0.1, 1.0),   // sigma
        safeFloat(0.1, 10),    // T
        (d1, sigma, T) => {
          const result = calcD2(d1, sigma, T)
          const expected = d1 - sigma * Math.sqrt(T)
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        },
      ),
    )
  })
})

// ═══ CP-J3-03: 等待期费用分摊累计 ═══
// **Validates: Requirements 4.2**
describe('Feature: j3-share-based-payment, Property CP-J3-03: 等待期累计费用', () => {
  it('CP-J3-03: calcCumulativeExpense(fv, vp, sy) === fv × MIN(sy/vp, 1)', () => {
    fc.assert(
      fc.property(
        safeFloat(0.01, 1e6),   // totalFV
        fc.integer({ min: 1, max: 5 }),  // vestingPeriod
        safeFloat(0, 5),        // serviceYears
        (totalFV, vestingPeriod, serviceYears) => {
          const result = calcCumulativeExpense(totalFV, vestingPeriod, serviceYears)
          const expected = totalFV * Math.min(serviceYears / vestingPeriod, 1)
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        },
      ),
    )
  })

  it('CP-J3-03b: 等待期满后累计费用=总公允', () => {
    fc.assert(
      fc.property(
        safeFloat(0.01, 1e6),
        fc.integer({ min: 1, max: 5 }),
        (totalFV, vestingPeriod) => {
          // serviceYears >= vestingPeriod → 累计 = totalFV
          const result = calcCumulativeExpense(totalFV, vestingPeriod, vestingPeriod + 1)
          expect(Math.abs(result - totalFV)).toBeLessThan(EPSILON)
        },
      ),
    )
  })
})

// ═══ CP-J3-04: 剩余费用=总FV-累计 ═══
// **Validates: Requirements 4.2**
describe('Feature: j3-share-based-payment, Property CP-J3-04: 剩余费用公式', () => {
  it('CP-J3-04: calcRemainingExpense(fv, cum) === fv - cum', () => {
    fc.assert(
      fc.property(
        safeFloat(0.01, 1e6),
        safeFloat(0, 1e6),
        (totalFV, cumulative) => {
          // 确保 cumulative <= totalFV（审计实务）
          const validCum = Math.min(cumulative, totalFV)
          const result = calcRemainingExpense(totalFV, validCum)
          const expected = totalFV - validCum
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        },
      ),
    )
  })
})

// ═══ CP-J3-05: 总公允=单位FV×数量 ═══
// **Validates: Requirements 2.2**
describe('Feature: j3-share-based-payment, Property CP-J3-05: 总公允价值公式', () => {
  it('CP-J3-05: calcTotalFairValue(u, q) === u × q', () => {
    fc.assert(
      fc.property(
        safeFloat(0.01, 1e4),
        fc.integer({ min: 1, max: 100000 }),
        (unitFV, quantity) => {
          const result = calcTotalFairValue(unitFV, quantity)
          const expected = unitFV * quantity
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        },
      ),
    )
  })
})

// ═══ CP-J3-06: 合计行恒等 ═══
// **Validates: Requirements 2.6**
describe('Feature: j3-share-based-payment, Property CP-J3-06: 合计行恒等', () => {
  it('CP-J3-06: calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        },
      ),
    )
  })
})
