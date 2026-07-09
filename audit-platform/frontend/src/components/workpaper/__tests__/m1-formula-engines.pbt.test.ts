/**
 * Property-Based Tests — M1 应付股利公式引擎（P1~P5）
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Tasks: 2.3 ~ 2.7
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5。
 * 科目：2232 应付股利（贷方/负债类！）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '../composables/useM1FormulaEngine'
import {
  calcFxConverted,
  calcFxDiff,
} from '../composables/useM1FxEngine'
import {
  calcDeclaredDividend,
} from '../composables/useM1DividendEngine'

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

// ─── P2: 负债类贷方期末余额 ─────────────────────────────────────────────────

describe('P2: 负债类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, cr, dr: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额(增加) - 借方发生额(减少)
   */
  it('calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, cr, dr) => {
          const result = calcLiabilityEndBalance(b, cr, dr)
          const expected = b + cr - dr
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P3: 外币折算 ───────────────────────────────────────────────────────────

describe('P3: 外币折算', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ amt, rate: calcFxConverted(amt, rate) === amt × rate
   * 折算本位币 = 原币金额 × 期末汇率
   */
  it('calcFxConverted(amt, rate) === amt * rate', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (amt, rate) => {
          const result = calcFxConverted(amt, rate)
          const expected = amt * rate
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 汇兑差异 ───────────────────────────────────────────────────────────

describe('P4: 汇兑差异', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ conv, booked: calcFxDiff(conv, booked) === conv - booked
   * 汇兑差异 = 折算本位币 - 账面本位币
   */
  it('calcFxDiff(conv, booked) === conv - booked', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (conv, booked) => {
          const result = calcFxDiff(conv, booked)
          const expected = conv - booked
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 应宣告股利 ─────────────────────────────────────────────────────────

describe('P5: 应宣告股利', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * ∀ profit, ratio: calcDeclaredDividend(profit, ratio) === profit × ratio
   * 应宣告股利 = 可供分配利润 × 分配比例
   */
  it('calcDeclaredDividend(profit, ratio) === profit * ratio', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (profit, ratio) => {
          const result = calcDeclaredDividend(profit, ratio)
          const expected = profit * ratio
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
   * **Validates: Requirements 7.5**
   *
   * ∀ arr: calcSubtotal(arr) === Σarr
   * 分类小计 = 数组所有元素之和
   */
  it('calcSubtotal(arr) === arr.reduce((s, v) => s + v, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true }), { minLength: 0, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
