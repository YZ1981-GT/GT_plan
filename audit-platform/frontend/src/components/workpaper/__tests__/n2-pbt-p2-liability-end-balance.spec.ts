/**
 * Property-Based Test — P2: 负债类期末余额（期初+贷-借）
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.5
 *
 * 使用 fast-check + vitest 验证 Correctness Property P2。
 * 科目：2221 应交税费（贷方/负债类）
 *
 * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额（计提/增加） - 借方发生额（缴纳/减少）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcLiabilityEndBalance } from '../composables/useN2FormulaEngine'

// ─── P2: 负债类期末余额（期初+贷-借） ──────────────────────────────────────

describe('P2: 负债类期末余额（期初+贷-借）', () => {
  /**
   * **Validates: Requirements 1.5**
   *
   * ∀ b, c, d ∈ [0, 1e9]:
   *   calcLiabilityEndBalance(b, c, d) === b + c - d
   *
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额（计提） - 借方发生额（缴纳）
   * 2221应交税费：贷增借减，期末=期初+计提-缴纳
   */
  it('calcLiabilityEndBalance(b, c, d) === b + c - d', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, c, d) => {
          const result = calcLiabilityEndBalance(b, c, d)
          const expected = b + c - d
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
