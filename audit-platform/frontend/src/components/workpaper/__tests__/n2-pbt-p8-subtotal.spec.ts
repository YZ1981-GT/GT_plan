/**
 * Property-Based Test — P8: 合计行恒等
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.11
 *
 * 使用 fast-check + vitest 验证 Correctness Property P8。
 * 合计行恒等：calcSubtotal(arr) === Σarr
 *
 * 用于：
 * - N2-1 审定表各税种行合计
 * - N2-2 明细表列小计（计提合计/缴纳合计/期末合计）
 * - N2-5 认定表汇总行
 *
 * **Validates: Requirements 1.5**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcSubtotal } from '../composables/useN2FormulaEngine'

// ─── P8: 合计行恒等 ────────────────────────────────────────────────────────

describe('P8: 合计行恒等 calcSubtotal(arr) === Σarr', () => {
  /**
   * **Validates: Requirements 1.5**
   *
   * ∀ arr: number[]:
   *   calcSubtotal(arr) === arr.reduce((s, x) => s + x, 0)
   *
   * 生成器：
   * - arr: fc.array(fc.float({min: -1e6, max: 1e6, noNaN: true}), {minLength: 0, maxLength: 50})
   */
  it('calcSubtotal(arr) === arr.reduce((s, x) => s + x, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((s, x) => s + x, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
