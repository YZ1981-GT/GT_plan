/**
 * useD3Adjustment PBT 测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D3-3 调整分录核心逻辑：借贷平衡检查。
 *
 * 测试纯函数逻辑（checkBalance），不依赖 Vue 响应式。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { checkBalance } from '../composables/useD3Adjustment'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 非负金额生成器：[0, 1e9] 有限浮点数 */
const nonNegAmountArb = fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })

/** 调整分录行借贷金额 record 生成器 */
const adjustmentRowAmountArb = fc.record({
  debitAmount: nonNegAmountArb,
  creditAmount: nonNegAmountArb,
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD3Adjustment - Property-Based Tests', () => {
  /**
   * **Feature: d3-prepaid-accounts, Property 15: 调整分录借贷平衡检查**
   *
   * For any 调整分录行列表，isBalanced应为true当且仅当所有行debitAmount之和
   * 等于所有行creditAmount之和。
   *
   * **Validates: Requirements 7.3**
   */
  describe('Property 15: 调整分录借贷平衡检查', () => {
    it('isBalanced === (debitTotal === creditTotal)', () => {
      fc.assert(
        fc.property(
          fc.array(adjustmentRowAmountArb, { minLength: 0, maxLength: 30 }),
          (rows) => {
            const result = checkBalance(rows)

            // debitTotal = SUM(debitAmount)
            const expectedDebitTotal = rows.reduce((sum, r) => sum + r.debitAmount, 0)
            expect(result.debitTotal).toBeCloseTo(expectedDebitTotal, 4)

            // creditTotal = SUM(creditAmount)
            const expectedCreditTotal = rows.reduce((sum, r) => sum + r.creditAmount, 0)
            expect(result.creditTotal).toBeCloseTo(expectedCreditTotal, 4)

            // isBalanced === (debitTotal === creditTotal)
            expect(result.isBalanced).toBe(result.debitTotal === result.creditTotal)

            // balanceDiff = debitTotal - creditTotal
            expect(result.balanceDiff).toBeCloseTo(result.debitTotal - result.creditTotal, 4)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('空数组时 isBalanced=true 且 totals 均为 0', () => {
      const result = checkBalance([])
      expect(result.debitTotal).toBe(0)
      expect(result.creditTotal).toBe(0)
      expect(result.isBalanced).toBe(true)
      expect(result.balanceDiff).toBe(0)
    })

    it('借贷相等的行列表 isBalanced=true', () => {
      fc.assert(
        fc.property(
          fc.array(nonNegAmountArb, { minLength: 1, maxLength: 20 }),
          (amounts) => {
            // Create rows where each row has same debit and credit
            const rows = amounts.map(amt => ({ debitAmount: amt, creditAmount: amt }))
            const result = checkBalance(rows)
            expect(result.isBalanced).toBe(true)
            expect(result.balanceDiff).toBe(0)
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
