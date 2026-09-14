/**
 * F1 Property 2 PBT: 审定数 = 未审 + AJE + RJE
 *
 * 验证核心公式：
 * - calcAuditedAmount(u, a, r) === u + a + r
 *
 * 适用于 F1-1 审定表所有行的审定金额计算（期初+期末均适用）。
 *
 * **Validates: Requirements 1.4, 2.3**
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { calcAuditedAmount } from '../composables/useF1FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

const signedFloatArb = fc.float({ min: -1e9, max: 1e9, noNaN: true })

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 2: 审定数 = 未审 + AJE + RJE', () => {
  /**
   * **Property 2: calcAuditedAmount(u, a, r) === u + a + r**
   *
   * 对任意 (unadjusted, aje, rje)，审定数等于三者之和。
   *
   * **Validates: Requirements 1.4, 2.3**
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        signedFloatArb,
        signedFloatArb,
        signedFloatArb,
        (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          return Math.abs(result - expected) < 1e-6
        },
      ),
      { numRuns: 100 },
    )
  })
})
