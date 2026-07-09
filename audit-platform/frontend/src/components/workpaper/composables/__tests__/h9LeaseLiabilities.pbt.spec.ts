/**
 * H9 租赁负债 — Property-Based Tests (P1-P5)
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Framework: fast-check + vitest
 *
 * **Validates: Requirements 2.3-2.5, 7.1-7.5**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
} from '../useH9FormulaEngine'
import {
  calcInterest,
  calcPrincipal,
  calcEndBalance,
} from '../useH9AmortizationEngine'

describe('H9 PBT Properties P1-P5', () => {
  /**
   * Property P1: 审定数公式链
   * ∀ u,a,r: calcAuditedAmount(u, a, r) === u + a + r
   * **Validates: Requirements 2.3**
   */
  it('Property P1: calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBe(u + a + r)
        }
      )
    )
  })

  /**
   * Property P2: 负债类期末余额（贷方科目）
   * ∀ b,cr,dr ≥ 0: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
   * **Validates: Requirements 2.4**
   */
  it('Property P2: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, cr, dr) => {
          expect(calcLiabilityEndBalance(b, cr, dr)).toBe(b + cr - dr)
        }
      )
    )
  })

  /**
   * Property P3: 实际利率法利息
   * ∀ balance≥0, rate∈[0,0.2]: calcInterest(balance, rate) === balance × rate
   * **Validates: Requirements 7.1**
   */
  it('Property P3: calcInterest(balance, rate) === balance × rate', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true }),
        fc.double({ min: 0, max: 0.2, noNaN: true }),
        (balance, rate) => {
          expect(calcInterest(balance, rate)).toBe(balance * rate)
        }
      )
    )
  })

  /**
   * Property P4: 本金拆分
   * ∀ payment > interest > 0: calcPrincipal(payment, interest) === payment - interest
   * **Validates: Requirements 7.2**
   */
  it('Property P4: calcPrincipal(payment, interest) === payment - interest', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e9, noNaN: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true }),
        (payment, interest) => {
          fc.pre(payment > interest)
          expect(calcPrincipal(payment, interest)).toBe(payment - interest)
        }
      )
    )
  })

  /**
   * Property P5: 期末余额递减
   * ∀ begin > principal > 0: calcEndBalance(begin, principal) === begin - principal
   * **Validates: Requirements 7.3**
   */
  it('Property P5: calcEndBalance(begin, principal) === begin - principal', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e9, noNaN: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true }),
        (begin, principal) => {
          fc.pre(begin > principal)
          expect(calcEndBalance(begin, principal)).toBe(begin - principal)
        }
      )
    )
  })
})

// ═══ P6-P8: 摊销表+现值引擎属性测试 ═══

import { generateSchedule } from '../useH9AmortizationEngine'
import { calcAnnuityPV, calcPresentValue } from '../useH9PVEngine'

describe('H9 PBT Properties P6-P8', () => {
  /**
   * Property P6: 摊销表终止余额趋零
   * ∀ initialBalance>0, rate∈(0.001,0.15), periods∈[2,60]:
   *   payment = annuity formula × 1.1 (ensures payoff)
   *   |generateSchedule(...).last.endBalance| < 1
   *
   * 引擎最后一期调整尾差，endBalance 应精确归零。
   * **Validates: Requirements 7.4, 7.5**
   */
  it('Property P6: |generateSchedule(...).last.endBalance| < 1', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 10000, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.001, max: 0.15, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 2, max: 60 }),
        (initialBalance, rate, periods) => {
          // 用年金公式计算最小还款额，确保能在periods内还清
          const minPayment = initialBalance * rate / (1 - Math.pow(1 + rate, -periods))
          const payment = minPayment * 1.1 // 10% over minimum
          const schedule = generateSchedule(initialBalance, payment, rate, periods)
          if (schedule.length === 0) return // guard
          const lastRow = schedule[schedule.length - 1]
          expect(Math.abs(lastRow.endBalance)).toBeLessThan(1)
        }
      ),
      { numRuns: 200 }
    )
  })

  /**
   * Property P7: 年金现值公式
   * ∀ payment>0, rate∈(0.001,0.2), periods∈[1,360]:
   *   calcAnnuityPV(p, r, n) ≈ p×(1-(1+r)^(-n))/r
   *
   * **Validates: Requirements 6.2**
   */
  it('Property P7: calcAnnuityPV(p, r, n) ≈ p×(1-(1+r)^-n)/r', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 100, max: 1e7, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.001, max: 0.2, noNaN: true, noDefaultInfinity: true }),
        fc.integer({ min: 1, max: 360 }),
        (payment, rate, periods) => {
          const expected = payment * (1 - Math.pow(1 + rate, -periods)) / rate
          const actual = calcAnnuityPV(payment, rate, periods)
          // Floating-point tolerance: relative error < 1e-10
          const relError = Math.abs(actual - expected) / (Math.abs(expected) || 1)
          expect(relError).toBeLessThan(1e-10)
        }
      ),
      { numRuns: 200 }
    )
  })

  /**
   * Property P8: 零利率现值恒等
   * ∀ payments[]: calcPresentValue(payments, 0) === Σpayments
   *
   * **Validates: Requirements 6.1**
   */
  it('Property P8: calcPresentValue(payments, 0) === Σpayments', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true }),
          { minLength: 1, maxLength: 120 }
        ),
        (payments) => {
          const sum = payments.reduce((a, b) => a + b, 0)
          expect(calcPresentValue(payments, 0)).toBe(sum)
        }
      ),
      { numRuns: 200 }
    )
  })
})
