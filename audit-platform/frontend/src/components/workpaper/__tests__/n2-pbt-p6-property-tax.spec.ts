/**
 * Property-Based Test — P6: 房产税从价=原值×(1-扣除比例)×1.2%
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.9
 *
 * 使用 fast-check + vitest 验证 Correctness Property P6。
 * 房产税从价计征 = 房产原值 × (1 - 扣除比例) × 1.2%
 *
 * 扣除比例由各省/自治区/直辖市确定，一般为 10%~30%（即 0.10~0.30）。
 *
 * **Validates: Requirements 6.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcPropertyTaxByValue } from '../composables/useN2MultiTaxEngine'

// ─── P6: 房产税从价 ──────────────────────────────────────────────────────

describe('P6: 房产税从价=原值×(1-扣除比例)×1.2%', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * ∀ ov∈R≥0, dr∈[0,0.3]:
   *   calcPropertyTaxByValue(ov, dr) === ov × (1 - dr) × 0.012
   *
   * 生成器：
   * - originalValue: fc.float({min: 0, max: 1e9, noNaN: true})
   * - deductRate: fc.float({min: 0, max: 0.3, noNaN: true})
   */
  it('calcPropertyTaxByValue(ov, dr) === ov × (1 - dr) × 0.012', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: Math.fround(1e9), noNaN: true }),
        fc.float({ min: 0, max: Math.fround(0.3), noNaN: true }),
        (ov, dr) => {
          const result = calcPropertyTaxByValue(ov, dr)
          const expected = ov * (1 - dr) * 0.012
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
