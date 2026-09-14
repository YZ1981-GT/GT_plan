/**
 * Property-Based Tests — M4 资本公积公式引擎 + 变动引擎（P1~P6）
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Tasks: 2.3 ~ 2.8
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5, P6。
 * 科目：4002 资本公积（**贷方/权益类！**）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M4资本公积（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM4FormulaEngine'
import {
  calcShareBasedDiff,
  aggregateReserve,
  type ReserveDetail,
} from '../composables/useM4ReserveEngine'

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

// ─── P3: 股份支付确认差异 ───────────────────────────────────────────────────

describe('P3: 股份支付确认差异', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ j3, booked: calcShareBasedDiff(j3, booked) === j3 - booked
   * 股份支付确认差异 = J3确认金额 - 账面其他资本公积增加
   */
  it('calcShareBasedDiff(j3, booked) === j3 - booked', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (j3, booked) => {
          const result = calcShareBasedDiff(j3, booked)
          const expected = j3 - booked
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 资本公积汇总 ───────────────────────────────────────────────────────

describe('P4: 资本公积汇总', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * ∀ details: aggregateReserve(details).total === aggregateReserve(details).premium + aggregateReserve(details).other
   * 资本公积总额 = 资本溢价 + 其他资本公积
   */
  it('aggregateReserve.total === premium + other', () => {
    const detailArb = fc.record({
      category: fc.constantFrom('premium' as const, 'other' as const),
      amount: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
    })

    fc.assert(
      fc.property(
        fc.array(detailArb, { minLength: 0, maxLength: 30 }),
        (details: ReserveDetail[]) => {
          const result = aggregateReserve(details)
          expect(result.total).toBeCloseTo(result.premium + result.other, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 小计求和 ───────────────────────────────────────────────────────────

describe('P5: 分类小计', () => {
  /**
   * **Validates: Requirements 6.3**
   *
   * ∀ arr: calcSubtotal(arr) === Σarr
   * 分类小计 = 数组所有元素之和（资本溢价/其他资本公积分类汇总）
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

// ─── P6: 按分类汇总守恒 ─────────────────────────────────────────────────────

describe('P6: 按分类汇总守恒', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * ∀ details: aggregateReserve(details).premium + aggregateReserve(details).other === Σ details[i].amount
   * 分类汇总之和（资本溢价+其他资本公积）恒等于明细金额总和（守恒性）
   */
  it('Σ aggregateReserve各分类 === Σ details.amount', () => {
    const detailArb = fc.record({
      category: fc.constantFrom('premium' as const, 'other' as const),
      amount: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
    })

    fc.assert(
      fc.property(
        fc.array(detailArb, { minLength: 0, maxLength: 30 }),
        (details: ReserveDetail[]) => {
          const result = aggregateReserve(details)
          const sumAll = details.reduce((s, d) => s + d.amount, 0)
          expect(result.premium + result.other).toBeCloseTo(sumAll, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
