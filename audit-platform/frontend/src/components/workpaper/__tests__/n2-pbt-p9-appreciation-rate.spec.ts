/**
 * Property-Based Test — P9: 土增税增值率=增值额/扣除项目
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 2.12
 *
 * 使用 fast-check + vitest 验证 Correctness Property P9。
 * 增值率 = 增值额 / 扣除项目金额
 * 当扣除项目金额=0时返回0（避免除零错误）
 *
 * **Validates: Requirements 7.4**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcAppreciationRate } from '../composables/useN2MultiTaxEngine'

// ─── P9: 土增税增值率 ──────────────────────────────────────────────────────

describe('P9: 土增税增值率=增值额/扣除项目', () => {
  /**
   * **Validates: Requirements 7.4**
   *
   * ∀ app∈R, di∈R>0:
   *   calcAppreciationRate(app, di) === app / di
   *
   * 生成器：
   * - app (增值额): fc.float({min: -1e9, max: 1e9, noNaN: true})
   * - di (扣除项目): fc.float({min: 1, max: 1e9, noNaN: true})（必须>0避免除零）
   */
  it('calcAppreciationRate(app, di) === app / di', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: 1, max: 1e9, noNaN: true }),
        (app, di) => {
          const result = calcAppreciationRate(app, di)
          const expected = app / di
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })

  /**
   * **Validates: Requirements 7.4**
   *
   * 边界情况：当 deductItems=0 时，返回 0（避免除零）
   */
  it('当 deductItems=0 时返回 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (app) => {
          const result = calcAppreciationRate(app, 0)
          expect(result).toBe(0)
        },
      ),
      { numRuns: 200 },
    )
  })
})
