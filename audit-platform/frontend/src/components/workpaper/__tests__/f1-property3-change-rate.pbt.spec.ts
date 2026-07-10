/**
 * F1 Property 3 PBT: 变动额与变动率公式
 *
 * 验证核心公式：
 * - calcChangeAmount(current, prior) === current - prior
 * - calcChangeRate 边界处理：期初=0且期末=0→''；期初=0→'N/A'；其他→(期末-期初)/期初
 *
 * **Validates: Requirements 2.4, 2.5, 13.4, 13.5**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcChangeAmount, calcChangeRate } from '../composables/useF1FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

const signedFloatArb = fc.float({ min: -1e9, max: 1e9, noNaN: true })

/** 非零浮点数（用于期初≠0场景） */
const nonZeroFloatArb = signedFloatArb.filter(v => v !== 0)

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 3: 变动额与变动率公式', () => {
  /**
   * **Property 3a: 变动额 === 期末 - 期初**
   *
   * 对任意 (current, prior)，calcChangeAmount 应返回差值。
   *
   * **Validates: Requirements 2.4, 13.4**
   */
  it('calcChangeAmount(current, prior) === current - prior', () => {
    fc.assert(
      fc.property(
        signedFloatArb,
        signedFloatArb,
        (current, prior) => {
          const result = calcChangeAmount(current, prior)
          const expected = current - prior
          return Math.abs(result - expected) < 1e-6
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 3b: 期初=0 且 期末=0 → 变动率为 ''**
   *
   * **Validates: Requirements 2.5, 13.5**
   */
  it('calcChangeRate(0, 0) === 空串', () => {
    expect(calcChangeRate(0, 0)).toBe('')
  })

  /**
   * **Property 3c: 期初=0 且 期末≠0 → 变动率为 "N/A"**
   *
   * **Validates: Requirements 2.5, 13.5**
   */
  it('calcChangeRate(0, nonZero) === "N/A"', () => {
    fc.assert(
      fc.property(
        nonZeroFloatArb,
        (current) => {
          return calcChangeRate(0, current) === 'N/A'
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 3d: 期初≠0 → 变动率 === (期末-期初)/期初**
   *
   * **Validates: Requirements 2.5, 13.5**
   */
  it('calcChangeRate(prior≠0, current) === (current - prior) / prior', () => {
    fc.assert(
      fc.property(
        nonZeroFloatArb,
        signedFloatArb,
        (prior, current) => {
          const result = calcChangeRate(prior, current)
          if (typeof result !== 'number') return false
          const expected = (current - prior) / prior
          return Math.abs(result - expected) < 1e-6
        },
      ),
      { numRuns: 100 },
    )
  })
})
