/**
 * Property-Based Test — P1: 审定数公式链
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.4
 *
 * 使用 fast-check + vitest 验证 Correctness Property P1。
 * 科目：2221 应交税费（贷方/负债类）
 *
 * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcAuditedAmount } from '../composables/useN2FormulaEngine'

// ─── P1: 审定数公式链 ───────────────────────────────────────────────────────

describe('P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 1.5**
   *
   * ∀ u, a, r ∈ [-1e9, 1e9]:
   *   calcAuditedAmount(u, a, r) === u + a + r
   *
   * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
   * N循环所有科目审定公式统一：E=B+C+D
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
