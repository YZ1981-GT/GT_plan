/**
 * Property-Based Tests — L6 专项应付款公式引擎
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Tasks: 2.2 ~ 2.6
 *
 * 使用 fast-check + vitest 验证 Correctness Properties。
 * 科目：2601 专项应付款（贷方/负债类！）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcDetailEndBalance,
  calcSubtotal,
  validateAdjudicationVsDetail,
} from '../composables/useL6FormulaEngine'

// ─── P2: 负债类贷方期末余额 ─────────────────────────────────────────────────

describe('P2: 负债类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, cr, dr: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额(拨入/增加) - 借方发生额(结转/返还/减少)
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
      { numRuns: 100 },
    )
  })
})

// ─── P3: 分类小计 ─────────────────────────────────────────────────────────────

describe('P3: 分类小计', () => {
  /**
   * **Validates: Requirements 1.2**
   *
   * ∀ arr (number[]): calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0)
   * 分类小计应等于数组元素之和。
   */
  it('calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ─── P4: 明细审定勾稽 ───────────────────────────────────────────────────────

describe('P4: 明细审定勾稽', () => {
  /**
   * **Validates: Requirements 2.5**
   *
   * 生成 N 条明细行，每行计算 end = calcDetailEndBalance(begin, creditIn, carryForward, refund)。
   * 将所有 end 聚合为 detailTotal = calcSubtotal(endBalances)。
   * 用同一 detailTotal 作为 adjTotal 传入 validateAdjudicationVsDetail → isMatch === true。
   *
   * 本质：当审定表合计 === 明细表合计时，勾稽一定通过。
   */
  it('Σ明细.期末 === 审定表合计.期末 → 勾稽一致', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.tuple(
            fc.float({ min: 0, max: 1e6, noNaN: true }), // begin
            fc.float({ min: 0, max: 1e6, noNaN: true }), // creditIn
            fc.float({ min: 0, max: 1e6, noNaN: true }), // carryForward
            fc.float({ min: 0, max: 1e6, noNaN: true }), // refund
          ),
          { minLength: 1, maxLength: 20 },
        ),
        (rows) => {
          // 计算每行期末余额
          const endBalances = rows.map(([begin, creditIn, carryForward, refund]) =>
            calcDetailEndBalance(begin, creditIn, carryForward, refund),
          )

          // 明细合计
          const detailTotal = calcSubtotal(endBalances)

          // 审定表合计 = 明细合计（构造一致场景）
          const adjTotal = calcSubtotal(endBalances)

          // 验证勾稽
          const result = validateAdjudicationVsDetail(adjTotal, detailTotal)
          expect(result.isMatch).toBe(true)
          expect(result.diff).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P5: 期末非负（专项应付款不应为负） ─────────────────────────────────────────

describe('P5: 期末非负', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * When begin ≥ 0, credit ≥ 0, and debit ≤ begin + credit,
   * then calcLiabilityEndBalance(b, cr, dr) >= 0
   *
   * 专项应付款不应为负：借方发生（结转/返还）不可能超过（期初+本期拨入），
   * 在合理业务约束下期末余额不为负数。
   */
  it('当 begin≥0, credit≥0, debit≤begin+credit 时，期末≥0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e6, noNaN: true }),
        fc.float({ min: 0, max: 1e6, noNaN: true }),
        fc.float({ min: 0, max: 2e6, noNaN: true }),
        (b, cr, dr) => {
          fc.pre(dr <= b + cr) // 约束：借方发生额不超过可用总额
          const result = calcLiabilityEndBalance(b, cr, dr)
          expect(result).toBeGreaterThanOrEqual(-0.01) // 浮点精度容差
        },
      ),
      { numRuns: 200 },
    )
  })
})
