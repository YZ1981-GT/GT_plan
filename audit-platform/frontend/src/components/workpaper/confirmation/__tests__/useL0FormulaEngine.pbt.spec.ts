/**
 * useL0FormulaEngine — Property-Based Tests (fast-check)
 *
 * P1: 区块合计 = Σ金额
 * P2: 还款检查比例 = 已检查还款/期末余额（除零→0）
 * P3: 对账差异 = 账面-对账单，自身差异 = 0
 * P4: 异常判定 ⟺ 账面≠对账单
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcBlockTotal,
  calcRepaymentRatio,
  calcReconcileDiff,
  isAbnormal,
} from '../l0-confirmation/composables/useL0FormulaEngine'

describe('useL0FormulaEngine — Property-Based Tests', () => {
  /**
   * Property 1: 区块合计=Σ金额
   * **Validates: Requirements 5.1, 2.7**
   */
  describe('P1: calcBlockTotal', () => {
    it('∀ amounts ∈ ℝ*: calcBlockTotal(amounts) === Σ amounts', () => {
      fc.assert(
        fc.property(
          fc.array(fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })),
          (amounts) => {
            const expected = amounts.reduce((a, b) => a + b, 0)
            const result = calcBlockTotal(amounts)
            // 浮点精度：使用相对误差比较
            if (Math.abs(expected) < 1e-10) {
              expect(Math.abs(result)).toBeLessThan(1e-10)
            } else {
              expect(Math.abs(result - expected) / Math.abs(expected)).toBeLessThan(1e-10)
            }
          },
        ),
        { numRuns: 100 },
      )
    })

    it('calcBlockTotal([]) === 0', () => {
      expect(calcBlockTotal([])).toBe(0)
    })
  })

  /**
   * Property 2: 还款检查比例=已检查还款/期末余额（除零→0）
   * **Validates: Requirements 5.2, 2.3**
   */
  describe('P2: calcRepaymentRatio', () => {
    it('∀ repaid≥0, balance∈ℝ: ratio === balance>0 ? repaid/balance : 0', () => {
      fc.assert(
        fc.property(
          fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          (repaid, balance) => {
            const result = calcRepaymentRatio(repaid, balance)
            if (balance === 0) {
              expect(result).toBe(0)
            } else {
              const expected = repaid / balance
              expect(result).toBe(expected)
            }
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  /**
   * Property 3: 对账差异=账面-对账单，自身差异=0
   * **Validates: Requirements 5.3**
   */
  describe('P3: calcReconcileDiff', () => {
    it('∀ book, statement ∈ ℝ: calcReconcileDiff(book, statement) === book - statement', () => {
      fc.assert(
        fc.property(
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          (book, statement) => {
            expect(calcReconcileDiff(book, statement)).toBe(book - statement)
          },
        ),
        { numRuns: 100 },
      )
    })

    it('零差异恒等: calcReconcileDiff(v, v) === 0', () => {
      fc.assert(
        fc.property(
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          (v) => {
            expect(calcReconcileDiff(v, v)).toBe(0)
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  /**
   * Property 4: 异常判定 ⟺ 账面≠对账单
   * **Validates: Requirements 5.4, 2.7**
   */
  describe('P4: isAbnormal', () => {
    it('∀ book, statement ∈ ℝ: isAbnormal(calcReconcileDiff(book, statement)) === (book !== statement)', () => {
      fc.assert(
        fc.property(
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          (book, statement) => {
            const diff = calcReconcileDiff(book, statement)
            const abnormal = isAbnormal(diff)
            expect(abnormal).toBe(book !== statement)
          },
        ),
        { numRuns: 100 },
      )
    })
  })
})
