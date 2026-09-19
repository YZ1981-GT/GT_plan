/**
 * useD5Adjustment PBT — Property 8: 调整分录借贷平衡检查
 *
 * Feature: d5-receivables-financing, Property 8: 调整分录借贷平衡检查
 * Generator: fc.array(fc.record({debit:fc.float({min:0,max:1e9}), credit:fc.float({min:0,max:1e9})}))
 * Assertion: isBalanced === (Math.abs(debitTotal - creditTotal) < 0.01)
 *
 * **Validates: Requirements 7.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { checkBalance } from '../composables/useD5Adjustment'

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD5Adjustment - Property-Based Tests', () => {
  /**
   * **Feature: d5-receivables-financing, Property 8: 调整分录借贷平衡检查**
   *
   * For any 调整分录行列表，isBalanced 应为 true 当且仅当
   * 所有行debitAmount之和与所有行creditAmount之和的差值绝对值 < 0.01。
   *
   * **Validates: Requirements 7.3**
   */
  describe('Property 8: 调整分录借贷平衡检查', () => {
    it('checkBalance.isBalanced === (Math.abs(debitTotal - creditTotal) < 0.01)', () => {
      fc.assert(
        fc.property(
          fc.array(
            fc.record({
              debitAmount: fc.float({ min: 0, max: 1e9, noNaN: true }),
              creditAmount: fc.float({ min: 0, max: 1e9, noNaN: true }),
            }),
            { minLength: 0, maxLength: 20 }
          ),
          (rows) => {
            const result = checkBalance(rows)

            // Manual calculation
            const expectedDebitTotal = rows.reduce((sum, r) => sum + r.debitAmount, 0)
            const expectedCreditTotal = rows.reduce((sum, r) => sum + r.creditAmount, 0)
            const expectedDiff = expectedDebitTotal - expectedCreditTotal
            const expectedIsBalanced = Math.abs(expectedDiff) < 0.01

            // Verify totals
            expect(result.debitTotal).toBeCloseTo(expectedDebitTotal, 5)
            expect(result.creditTotal).toBeCloseTo(expectedCreditTotal, 5)
            expect(result.balanceDiff).toBeCloseTo(expectedDiff, 5)

            // Verify isBalanced logic
            expect(result.isBalanced).toBe(expectedIsBalanced)
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
