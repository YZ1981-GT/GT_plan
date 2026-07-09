/**
 * Property-Based Test — P4: 应交增值税=销项-(进项-进项转出)
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.7
 *
 * 使用 fast-check + vitest 验证 Correctness Property P4。
 * 科目：2221-01 应交增值税（N2-6 增值税测算表核心）
 *
 * 应交增值税 = 销项税额 - (进项税额 - 进项转出)
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcPayableVat } from '../composables/useN2VatEngine'

// ─── P4: 应交增值税=销项-(进项-进项转出) ────────────────────────────────────

describe('P4: 应交增值税=销项-(进项-进项转出)', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ out, inp, trans ∈ [0, 1e9]:
   *   calcPayableVat(out, inp, trans) === out - (inp - trans)
   *
   * 应交增值税 = 销项税额 - (进项税额 - 进项转出)
   * 净进项 = 进项 - 进项转出（实际可抵扣额）
   * 应交 = 销项 - 净进项
   * 结果可负（留抵税额）
   */
  it('calcPayableVat(out, inp, trans) === out - (inp - trans)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (out, inp, trans) => {
          const result = calcPayableVat(out, inp, trans)
          const expected = out - (inp - trans)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
