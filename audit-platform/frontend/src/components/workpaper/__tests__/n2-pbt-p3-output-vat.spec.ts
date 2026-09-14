/**
 * Property-Based Test — P3: 增值税销项税额=销售额×税率
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.6
 *
 * 使用 fast-check + vitest 验证 Correctness Property P3。
 * 科目：2221-01 应交增值税（N2-6 增值税测算表核心）
 *
 * 销项税额 = 不含税销售额 × 适用税率
 * 一般纳税人常见税率：13%/9%/6%；小规模：3%
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcOutputVat } from '../composables/useN2VatEngine'

// ─── P3: 增值税销项税额=销售额×税率 ────────────────────────────────────────

describe('P3: 增值税销项税额=销售额×税率', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ sales ∈ [0, 1e9], rate ∈ [0, 0.17]:
   *   calcOutputVat(sales, rate) === sales × rate
   *
   * 销项税额 = 销售额 × 适用税率
   * 来源：N2-6 增值税测算表
   */
  it('calcOutputVat(sales, rate) === sales × rate', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: Math.fround(1e9), noNaN: true }),
        fc.float({ min: 0, max: Math.fround(0.17), noNaN: true }),
        (sales, rate) => {
          const result = calcOutputVat(sales, rate)
          const expected = sales * rate
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
