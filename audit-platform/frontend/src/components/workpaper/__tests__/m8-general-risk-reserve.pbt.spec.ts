/**
 * Property-Based Tests — M8 一般风险准备公式引擎 + 风险引擎（P1~P5）
 *
 * @feature m8-general-risk-reserve
 * @property P1, P2, P3, P4, P5
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Tasks: 2.3 ~ 2.7
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5。
 * 科目：4104 一般风险准备（**贷方/权益类！**）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M8一般风险准备（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：      期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM8FormulaEngine'
import {
  calcRiskProvision,
  calcProvisionDiff,
} from '../composables/useM8RiskEngine'

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

// ─── P2: 权益类期末余额（贷方！） ───────────────────────────────────────────

describe('P2: 权益类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, cr, dr: calcEquityEndBalance(b, cr, dr) === b + cr - dr
   * 权益类（贷方科目）期末余额 = 期初 + 贷方发生额(计提增加) - 借方发生额(转回/使用减少)
   *
   * 生成器：fc.float({min:0, max:1e9}) × 3（权益类余额非负）
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

// ─── P3: 风险资产计提 ───────────────────────────────────────────────────────

describe('P3: 风险资产计提', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * ∀ ra, rate: calcRiskProvision(ra, rate) === ra × rate
   * 应计提余额 = 风险资产期末余额 × 计提比例（≥1.5%）
   */
  it('calcRiskProvision(ra, rate) === ra * rate', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (ra, rate) => {
          const result = calcRiskProvision(ra, rate)
          const expected = ra * rate
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 计提差异 ───────────────────────────────────────────────────────────

describe('P4: 计提差异', () => {
  /**
   * **Validates: Requirements 3.5**
   *
   * ∀ est, booked: calcProvisionDiff(est, booked) === est - booked
   * 计提差异 = 应计提金额 - 账面已计提金额（正=计提不足，负=超额计提）
   */
  it('calcProvisionDiff(est, booked) === est - booked', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (est, booked) => {
          const result = calcProvisionDiff(est, booked)
          const expected = est - booked
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 小计求和 ───────────────────────────────────────────────────────────

describe('P5: 分类小计', () => {
  /**
   * **Validates: Requirements 6.4**
   *
   * ∀ arr: calcSubtotal(arr) === Σarr
   * 分类小计 = 数组所有元素之和（一般风险准备分类汇总）
   */
  it('calcSubtotal(arr) === arr.reduce((s, v) => s + v, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 50 }),
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
