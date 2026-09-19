/**
 * Property-Based Tests — M7 专项储备公式引擎 + 计提引擎
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Tasks: 2.3 ~ 2.8
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P6。
 * 科目：4201 专项储备（**贷方/权益类！**）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M7专项储备（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM7FormulaEngine'

// ─── P1: 审定数公式链 ───────────────────────────────────────────────────────

describe('P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * ∀ u, a, r: calcAuditedAmount(u, a, r) === u + a + r
   * 审定数 = 未审数 + 审计调整(AJE) + 重分类调整(RJE)
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P2: 权益类贷方期末余额 ─────────────────────────────────────────────────

describe('P2: 权益类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4, 7.4**
   *
   * ∀ b, cr, dr ∈ float[0, 1e9]: calcEquityEndBalance(b, cr, dr) === b + cr - dr
   * 权益类期末 = 期初 + 贷方(计提) - 借方(使用)
   *
   * ⚠️ 权益类贷方方向：与资产类(期初+借-贷)完全相反！
   */
  it('calcEquityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, cr, dr) => {
          const result = calcEquityEndBalance(b, cr, dr)
          const expected = b + cr - dr
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P6: 分类小计 ───────────────────────────────────────────────────────────

describe('P6: 分类小计', () => {
  /**
   * **Validates: Requirements calcSubtotal**
   *
   * ∀ arr (array of float): calcSubtotal(arr) === Σarr
   */
  it('calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true }), { minLength: 0, maxLength: 20 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((sum, v) => sum + v, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
