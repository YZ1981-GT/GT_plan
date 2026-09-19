/**
 * F1 Property 5 PBT: 变动率阈值高亮判定
 *
 * 验证核心逻辑：
 * - isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)（数值型）
 * - isChangeRateExceeding('', 0.3) === false（空串→无法判定）
 * - isChangeRateExceeding('N/A', 0.3) === false（N/A→无法判定）
 *
 * **Validates: Requirements 2.7, 13.7**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { isChangeRateExceeding } from '../composables/useF1FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

const rateFloatArb = fc.float({ min: -10, max: 10, noNaN: true })

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 5: 变动率阈值高亮判定', () => {
  /**
   * **Property 5a: 数值型变动率 → Math.abs(r) > threshold**
   *
   * 对任意数值变动率 r，isChangeRateExceeding(r, 0.3) 等价于 |r| > 0.3。
   *
   * **Validates: Requirements 2.7, 13.7**
   */
  it('isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)', () => {
    fc.assert(
      fc.property(rateFloatArb, (r) => {
        const result = isChangeRateExceeding(r, 0.3)
        const expected = Math.abs(r) > 0.3
        return result === expected
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 5b: 空串和'N/A' → false**
   *
   * **Validates: Requirements 2.7, 13.7**
   */
  it('空串 → false', () => {
    expect(isChangeRateExceeding('', 0.3)).toBe(false)
  })

  it('"N/A" → false', () => {
    expect(isChangeRateExceeding('N/A', 0.3)).toBe(false)
  })
})
