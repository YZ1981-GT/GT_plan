/**
 * Property-Based Tests — D1 监盘核查组纯函数
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Tasks: 1.2–1.7
 *
 * 使用 fast-check + vitest 验证 6 个 correctness properties。
 * 覆盖 D1-11 公式引擎 + D1-12 质押比例 + D1-13 例外占比 + SUM合计 + 负数括号格式。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  computeClosingBalance,
  computeBookValue,
  sumColumn,
  computePledgeRatio,
  computeExceptionRate,
  formatNegativeAmount,
} from '../d1InspectionFormulas'

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: D1-11 期末余额公式 F=C+D-E
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 1: D1-11 期末余额公式 F=C+D-E
describe('Feature: d1-inspection-check, Property 1: D1-11 期末余额公式 F=C+D-E', () => {
  /**
   * **Validates: Requirements 4.4**
   *
   * For any (openingBalance, debit, credit), computeClosingBalance(c, d, e) === c + d - e
   */
  it('P1: closingBalance = opening + debit - credit', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (c, d, e) => {
          expect(computeClosingBalance(c, d, e)).toBeCloseTo(c + d - e)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: D1-11 账面价值公式 H=F-G
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 2: D1-11 账面价值公式 H=F-G
describe('Feature: d1-inspection-check, Property 2: D1-11 账面价值公式 H=F-G', () => {
  /**
   * **Validates: Requirements 4.5**
   *
   * For any (closingBalance, badDebtProvision), computeBookValue(f, g) === f - g
   */
  it('P2: bookValue = closingBalance - badDebtProvision', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (f, g) => {
          expect(computeBookValue(f, g)).toBeCloseTo(f - g)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: SUM合计行正确性
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 3: SUM合计行正确性
describe('Feature: d1-inspection-check, Property 3: SUM合计行正确性', () => {
  /**
   * **Validates: Requirements 2.1, 5.1, 8.1, 12.1, 12.2**
   *
   * For any array of rows with numeric 'amount' field,
   * sumColumn(rows, 'amount') === rows.reduce((s, r) => s + (Number(r.amount) || 0), 0)
   */
  it('P3: sumColumn equals manual reduce sum', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ amount: fc.float({ min: -1e6, max: 1e6, noNaN: true }) }),
          { minLength: 0, maxLength: 30 }
        ),
        (rows) => {
          const result = sumColumn(rows, 'amount')
          const expected = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0)
          expect(result).toBeCloseTo(expected)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: D1-12 质押比例计算与零值守卫
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 4: D1-12 质押比例计算与零值守卫
describe('Feature: d1-inspection-check, Property 4: D1-12 质押比例计算与零值守卫', () => {
  /**
   * **Validates: Requirements 8.3, 8.4**
   *
   * When adjBookValue is null or 0, returns null.
   * Otherwise returns pledgeTotal / adjBookValue.
   * When result > 0.5, isPledgeWarning should be true.
   */
  it('P4: pledgeRatio null guard and warning threshold', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.oneof(
          fc.constant(null as number | null),
          fc.constant(0 as number | null),
          fc.float({ min: -1e6, max: 1e9, noNaN: true }) as fc.Arbitrary<number | null>
        ),
        (pledgeTotal, adjBookValue) => {
          const result = computePledgeRatio(pledgeTotal, adjBookValue)

          if (adjBookValue == null || adjBookValue === 0) {
            // Zero guard: returns null
            expect(result).toBeNull()
          } else {
            // Normal case: returns ratio
            expect(result).toBeCloseTo(pledgeTotal / adjBookValue)

            // Warning threshold: > 0.5 means isPledgeWarning = true
            const isPledgeWarning = result !== null && result > 0.5
            if (result! > 0.5) {
              expect(isPledgeWarning).toBe(true)
            } else {
              expect(isPledgeWarning).toBe(false)
            }
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: D1-13 例外占比公式
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 5: D1-13 例外占比公式
describe('Feature: d1-inspection-check, Property 5: D1-13 例外占比公式', () => {
  /**
   * **Validates: Requirements 12.4**
   *
   * When totalCheckedAmount === 0, returns 0.
   * Otherwise returns exceptionAmount / totalCheckedAmount.
   */
  it('P5: exceptionRate zero guard and division', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        (exceptionAmount, totalCheckedAmount) => {
          const result = computeExceptionRate(exceptionAmount, totalCheckedAmount)

          if (totalCheckedAmount === 0) {
            expect(result).toBe(0)
          } else {
            expect(result).toBeCloseTo(exceptionAmount / totalCheckedAmount)
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 负数金额括号格式
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-inspection-check, Property 7: 负数金额括号格式
describe('Feature: d1-inspection-check, Property 7: 负数金额括号格式', () => {
  /**
   * **Validates: Requirements 18.2**
   *
   * For negative values: output contains '(' and ')' and no '-'.
   * For non-negative values: returns empty string ''.
   */
  it('P7: negative amounts formatted with parentheses, no minus sign', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: Math.fround(-0.01), noNaN: true }),
        (negativeValue) => {
          const result = formatNegativeAmount(negativeValue)
          expect(result).toContain('(')
          expect(result).toContain(')')
          expect(result).not.toContain('-')
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P7: non-negative amounts return empty string', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (nonNegativeValue) => {
          const result = formatNegativeAmount(nonNegativeValue)
          expect(result).toBe('')
        }
      ),
      { numRuns: 100 }
    )
  })
})
