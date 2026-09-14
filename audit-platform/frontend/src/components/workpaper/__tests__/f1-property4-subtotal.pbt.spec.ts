/**
 * F1 Property 4 PBT: 合计行 = SUM(明细行)
 *
 * 验证核心公式：
 * - calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0)
 *
 * 通用求和逻辑，适用于 F1-1/F1-2/F1-5/F1-6/F1-7 所有合计行。
 *
 * **Validates: Requirements 2.4, 13.6**
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { calcSubtotal } from '../composables/useF1FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

const numArrayArb = fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true }), {
  minLength: 1,
  maxLength: 50,
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 4: 合计行 = SUM(明细行)', () => {
  /**
   * **Property 4: calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0)**
   *
   * 对任意非空数值数组，calcSubtotal 应返回所有元素之和。
   *
   * **Validates: Requirements 2.4, 13.6**
   */
  it('calcSubtotal(arr) === arr.reduce((a,b) => a+b, 0)', () => {
    fc.assert(
      fc.property(numArrayArb, (arr) => {
        const result = calcSubtotal(arr)
        const expected = arr.reduce((a, b) => a + b, 0)
        return Math.abs(result - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })
})
