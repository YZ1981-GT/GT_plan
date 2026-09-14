/**
 * Property-Based Tests — M5 盈余公积公式引擎 + 计提引擎（P1~P6）
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Tasks: 2.3 ~ 2.8
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5, P6。
 * 科目：4101 盈余公积（**贷方/权益类！**）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M5盈余公积（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM5FormulaEngine'
import {
  calcStatutoryAccrual,
  calcAccrualDiff,
  isAccrualCeilingReached,
} from '../composables/useM5AccrualEngine'

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
   * 权益类（贷方科目）期末余额 = 期初 + 贷方发生额(增加) - 借方发生额(减少)
   *
   * ⚠️ 与M3库存股（借方备抵类）方向相反！
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

// ─── P3: 法定盈余公积10%计提 ────────────────────────────────────────────────

describe('P3: 法定盈余公积10%计提', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ base: calcStatutoryAccrual(base) === base × 0.1
   * 法定盈余公积 = 计提基数（净利润-弥补亏损） × 10%
   */
  it('calcStatutoryAccrual(base) === base * 0.1', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (base) => {
          const result = calcStatutoryAccrual(base)
          const expected = base * 0.1
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
   * **Validates: Requirements 4.4**
   *
   * ∀ est, booked: calcAccrualDiff(est, booked) === est - booked
   * 计提差异 = 应计提金额 - 账面已计提金额（正=少提，负=多提）
   */
  it('calcAccrualDiff(est, booked) === est - booked', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (est, booked) => {
          const result = calcAccrualDiff(est, booked)
          const expected = est - booked
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 注册资本50%计提上限 ────────────────────────────────────────────────

describe('P5: 注册资本50%计提上限', () => {
  /**
   * **Validates: Requirements 4.5**
   *
   * ∀ acc(≥0), cap(>0): isAccrualCeilingReached(acc, cap) ⟺ acc ≥ cap × 0.5
   * 累计法定盈余公积≥注册资本50%时可不再计提
   */
  it('isAccrualCeilingReached(acc, cap) === (acc >= cap * 0.5)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: Math.fround(1), max: 1e9, noNaN: true }),
        (acc, cap) => {
          const result = isAccrualCeilingReached(acc, cap)
          const expected = acc >= cap * 0.5
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P6: 分类小计 ───────────────────────────────────────────────────────────

describe('P6: 分类小计', () => {
  /**
   * **Validates: Requirements 6.4**
   *
   * ∀ arr: calcSubtotal(arr) === Σarr
   * 分类小计 = 数组所有元素之和（法定/任意盈余公积分类汇总）
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
