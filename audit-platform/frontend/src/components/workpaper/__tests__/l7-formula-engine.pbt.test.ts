/**
 * Property-Based Tests — L7 其他非流动负债公式引擎
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Tasks: 2.2 ~ 2.6
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5。
 * 科目：2801 其他非流动负债（贷方/负债类！）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  validateAdjudicationVsDetail,
} from '../composables/useL7FormulaEngine'

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
      { numRuns: 100 },
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
      { numRuns: 100 },
    )
  })
})

// ─── P3: 分类小计 ───────────────────────────────────────────────────────────

describe('P3: 分类小计', () => {
  /**
   * **Validates: Requirements 5.1**
   *
   * ∀ arr: calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0)
   * 数组求和（按项目/分类汇总）
   */
  it('calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 20 }),
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
   * 当明细项目期末余额之和 === 审定表合计时，isMatch === true
   * 生成器：生成明细项目数组(begin/increase/decrease)，求和期末余额作为total
   */
  it('validateAdjudicationVsDetail(total, total).isMatch === true', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            begin: fc.float({ min: 0, max: 1e6, noNaN: true }),
            increase: fc.float({ min: 0, max: 1e6, noNaN: true }),
            decrease: fc.float({ min: 0, max: 1e6, noNaN: true }),
          }),
          { minLength: 1, maxLength: 10 },
        ),
        (details) => {
          // 计算每个明细项目的期末余额之和
          const detailTotal = details.reduce(
            (sum, d) => sum + (d.begin + d.increase - d.decrease),
            0,
          )
          // 当审定表合计 === 明细合计时，勾稽一致
          const result = validateAdjudicationVsDetail(detailTotal, detailTotal)
          expect(result.isMatch).toBe(true)
          expect(result.diff).toBeCloseTo(0, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P5: 期末非负 ───────────────────────────────────────────────────────────

describe('P5: 期末非负', () => {
  /**
   * **Validates: Requirements 5.3**
   *
   * 当 begin≥0, credit≥0, debit∈[0, begin+credit] 时，
   * calcLiabilityEndBalance(b, cr, dr) >= 0
   * 其他非流动负债期末不应为负（约束生成器保证合法输入）
   */
  it('calcLiabilityEndBalance(b, cr, dr) >= 0 when debit ≤ begin + credit', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1, noNaN: true }),
        (begin, credit, drRatio) => {
          // debit 约束在 [0, begin + credit] 之间，确保期末非负
          const maxDebit = begin + credit
          const debit = drRatio * maxDebit
          const result = calcLiabilityEndBalance(begin, credit, debit)
          expect(result).toBeGreaterThanOrEqual(-0.001) // 浮点容差
        },
      ),
      { numRuns: 100 },
    )
  })
})
