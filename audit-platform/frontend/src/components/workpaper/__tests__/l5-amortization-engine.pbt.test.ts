/**
 * Property-Based Tests — L5 长期应付款摊销引擎
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Tasks: 2.7 ~ 2.9
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P5, P6, P7。
 * 核心：未确认融资费用实际利率法摊销（CAS 21/22）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAmortization,
  generateSchedule,
} from '../composables/useL5AmortizationEngine'

// ─── P5: 实际利率法摊销 ──────────────────────────────────────────────────────

describe('P5: 实际利率法摊销', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ amortizedCost > 0, eir ∈ (0, 0.2):
   *   calcAmortization(cost, eir) === cost × eir
   *
   * 确认的融资费用 = 期初摊余成本 × 实际利率
   */
  it('calcAmortization(cost, eir) === cost × eir', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true }),
        fc.double({ min: 0.001, max: 0.2, noNaN: true }),
        (amortizedCost, eir) => {
          const result = calcAmortization(amortizedCost, eir)
          const expected = amortizedCost * eir
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P6: 零利率摊销恒等 ─────────────────────────────────────────────────────

describe('P6: EIR=0时摊销为0', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ cost > 0: calcAmortization(cost, 0) === 0
   * EIR=0 时无融资费用，全部付款偿还本金。
   */
  it('calcAmortization(cost, 0) === 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true }),
        (cost) => {
          const result = calcAmortization(cost, 0)
          expect(result).toBe(0)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P7: 摊销表终值趋零 ─────────────────────────────────────────────────────

describe('P7: 摊销表末期未确认余额≈0', () => {
  /**
   * **Validates: Requirements 4.4**
   *
   * ∀ initialCost, repayments, eir, periods（自洽）:
   *   |generateSchedule(...).last.endCost| < 1
   *
   * 摊销表最后一期的期末摊余成本应趋向0（允许±1元尾差）。
   * 生成器策略：等额还款使 repayment ≈ initialCost/periods × (1+eir)
   */
  it('|generateSchedule(...).last.endCost| < 1', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1000, max: 1e7, noNaN: true }),
        fc.double({ min: 0.01, max: 0.15, noNaN: true }),
        fc.integer({ min: 2, max: 10 }),
        (initialCost, eir, periods) => {
          // 自洽还款：等额还款使摊销表可行
          const repayment = (initialCost / periods) * (1 + eir)
          const repayments = Array.from({ length: periods }, () => repayment)

          const schedule = generateSchedule(initialCost, repayments, eir, periods)

          // 摊销表非空
          expect(schedule.length).toBe(periods)

          // 最后一期期末余额≈0（尾差调整保证为0）
          const lastRow = schedule[schedule.length - 1]
          expect(Math.abs(lastRow.endCost)).toBeLessThan(1)
        },
      ),
      { numRuns: 5 },
    )
  })
})
