/**
 * Property-Based Test — P5: 城建税及附加=(增值税+消费税)×税率
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.8
 *
 * 使用 fast-check + vitest 验证 Correctness Property P5。
 * 城建税及附加 = (增值税 + 消费税) × 适用税率
 *
 * 适用税率：
 * - 城市维护建设税：市区 7% / 县城、镇 5% / 其他 1%
 * - 教育费附加：3%
 * - 地方教育附加：2%
 *
 * **Validates: Requirements 5.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcSurtax } from '../composables/useN2MultiTaxEngine'

// ─── P5: 城建税及附加 ──────────────────────────────────────────────────────

describe('P5: 城建税及附加=(增值税+消费税)×税率', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * ∀ vat∈R≥0, ct∈R≥0, rate∈{0.07,0.05,0.01,0.03,0.02}:
   *   calcSurtax(vat, ct, rate) === (vat + ct) × rate
   *
   * 生成器：
   * - vat, consumptionTax: fc.float({min: 0, max: 1e9, noNaN: true})
   * - rate: fc.constantFrom(0.07, 0.05, 0.01, 0.03, 0.02)
   */
  it('calcSurtax(vat, ct, rate) === (vat + ct) × rate', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.constantFrom(0.07, 0.05, 0.01, 0.03, 0.02),
        (vat, ct, rate) => {
          const result = calcSurtax(vat, ct, rate)
          const expected = (vat + ct) * rate
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
