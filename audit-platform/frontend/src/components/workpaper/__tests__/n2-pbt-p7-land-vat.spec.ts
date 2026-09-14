/**
 * Property-Based Test — P7: 土地增值税=增值额×税率-扣除项目×速算扣除系数
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.10
 *
 * 使用 fast-check + vitest 验证 Correctness Property P7。
 * 土地增值税 = 增值额 × 适用税率 - 扣除项目金额 × 速算扣除系数
 *
 * 四级超率累进税率：
 * | 增值率        | 税率 | 速算扣除系数 |
 * |--------------|------|------------|
 * | ≤50%         | 30%  | 0%         |
 * | 50%~100%     | 40%  | 5%         |
 * | 100%~200%    | 50%  | 15%        |
 * | >200%        | 60%  | 35%        |
 *
 * **Validates: Requirements 7.2**
 * **Feature: n2-taxes-payable, Property P7: 土地增值税=增值额×税率-扣除项目×速算扣除系数**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcLandVat } from '../composables/useN2MultiTaxEngine'

// ─── P7: 土地增值税 ──────────────────────────────────────────────────────

describe('P7: 土地增值税=增值额×税率-扣除项目×速算扣除系数', () => {
  /**
   * **Validates: Requirements 7.2**
   *
   * ∀ app∈R≥0, di∈R≥0, rate∈{0.3,0.4,0.5,0.6}, coef∈{0,0.05,0.15,0.35}:
   *   calcLandVat(app, rate, di, coef) === app × rate - di × coef
   *
   * 生成器：
   * - app (增值额): fc.float({min: 0, max: 1e9, noNaN: true})
   * - di (扣除项目): fc.float({min: 0, max: 1e9, noNaN: true})
   * - rate (四级累进税率): fc.constantFrom(0.3, 0.4, 0.5, 0.6)
   * - coef (速算扣除系数): fc.constantFrom(0, 0.05, 0.15, 0.35)
   */
  it('calcLandVat(app, rate, di, coef) === app × rate - di × coef', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.constantFrom(0.3, 0.4, 0.5, 0.6),
        fc.constantFrom(0, 0.05, 0.15, 0.35),
        (app, di, rate, coef) => {
          const result = calcLandVat(app, rate, di, coef)
          const expected = app * rate - di * coef
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
