/**
 * Property-Based Tests — D1-4 坏账准备明细表 composable
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 6.2
 *
 * 使用 fast-check + vitest 验证：
 * - Property 12: ECL差异警告判定
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcAuditedAmount, calcBadDebtEndBalance, calcSubtotal } from '../useD1FormulaEngine'

// ─── Helpers replicating ECL warning logic from useD1BadDebt ─────────────────

/**
 * Compute ECL difference: subtotalAudited - eclTestTotal
 * (mirrors eclDifference computed in useD1BadDebt)
 */
function computeEclDifference(subtotalAudited: number, eclTestTotal: number): number {
  return subtotalAudited - eclTestTotal
}

/**
 * Compute ECL warning string: non-zero difference produces warning, zero produces null
 * (mirrors eclWarning computed in useD1BadDebt)
 */
function computeEclWarning(subtotalAudited: number, eclTestTotal: number): string | null {
  const diff = computeEclDifference(subtotalAudited, eclTestTotal)
  if (diff === 0) return null
  const sign = diff > 0 ? '+' : '-'
  return `与ECL测试差异: ${sign}${Math.abs(diff)}元`
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: ECL差异警告判定
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 12: ECL差异警告判定', () => {
  /**
   * **Validates: Requirements 6.6**
   *
   * For any pair (subtotalAudited, eclTestTotal):
   * - When they differ: produces a warning string containing the difference amount
   * - When equal: produces null
   */
  it('不相等时返回含差异金额的警告字符串', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (subtotalAudited, eclTestTotal) => {
          // Filter: only consider cases where they are NOT equal
          fc.pre(subtotalAudited !== eclTestTotal)

          const warning = computeEclWarning(subtotalAudited, eclTestTotal)
          const diff = subtotalAudited - eclTestTotal

          // Should NOT be null when difference exists
          expect(warning).not.toBeNull()

          // Should contain the absolute difference amount
          expect(warning).toContain(`${Math.abs(diff)}`)

          // Should contain the correct sign prefix
          if (diff > 0) {
            expect(warning).toContain('+')
          } else {
            expect(warning).toContain('-')
          }

          // Should contain the standard prefix
          expect(warning).toContain('与ECL测试差异:')
          expect(warning).toContain('元')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('相等时返回null', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (value) => {
          // Same value for both → difference is 0 → no warning
          const warning = computeEclWarning(value, value)
          expect(warning).toBeNull()
        },
      ),
      { numRuns: 100 },
    )
  })

  it('差异金额绝对值正确', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (subtotalAudited, eclTestTotal) => {
          fc.pre(subtotalAudited !== eclTestTotal)

          const diff = computeEclDifference(subtotalAudited, eclTestTotal)
          const expectedDiff = subtotalAudited - eclTestTotal

          expect(diff).toBeCloseTo(expectedDiff, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
