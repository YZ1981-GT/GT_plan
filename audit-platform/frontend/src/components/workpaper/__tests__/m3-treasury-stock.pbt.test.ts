/**
 * Property-Based Tests — M3 库存股公式引擎（P1~P6）
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Tasks: 2.3 ~ 2.8
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5, P6。
 * 科目：4002 库存股（**借方/权益备抵类！**）
 *
 * ⚠️ 方向与其他M权益类（M2/M4/M5/M6/M7/M8/M9/M10）完全相反！
 *   其他M权益类（贷方科目）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcContraEquityEndBalance,
  calcSubtotal,
} from '../composables/useM3FormulaEngine'
import { calcFxConverted } from '../composables/useM3FxEngine'
import { calcRepurchaseAmount, calcCancelDiff } from '../composables/useM3TreasuryEngine'

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

// ─── P2: 权益备抵类期末余额（借方！） ───────────────────────────────────────

describe('P2: 权益备抵类期末余额（借方！）', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, dr, cr: calcContraEquityEndBalance(b, dr, cr) === b + dr - cr
   * 权益备抵类（借方科目）期末余额 = 期初 + 借方发生额(回购增加) - 贷方发生额(注销/再售减少)
   *
   * ⚠️ 与M2/M4/M5/M6等权益类（贷方增加）方向相反！
   */
  it('calcContraEquityEndBalance(b, dr, cr) === b + dr - cr', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, dr, cr) => {
          const result = calcContraEquityEndBalance(b, dr, cr)
          const expected = b + dr - cr
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P3: 回购金额 ───────────────────────────────────────────────────────────

describe('P3: 回购金额', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * ∀ shares, price: calcRepurchaseAmount(shares, price) === shares × price
   * 回购金额 = 回购股数 × 回购单价
   */
  it('calcRepurchaseAmount(shares, price) === shares * price', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (shares, price) => {
          const result = calcRepurchaseAmount(shares, price)
          const expected = shares * price
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 注销冲减差额 ───────────────────────────────────────────────────────

describe('P4: 注销冲减差额', () => {
  /**
   * **Validates: Requirements 5.4**
   *
   * ∀ ca, dc, dr: calcCancelDiff(ca, dc, dr) === ca - dc - dr
   * 注销冲减差额 = 注销金额 - 冲减实收资本(M2) - 冲减资本公积(M4)
   */
  it('calcCancelDiff(ca, dc, dr) === ca - dc - dr', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (ca, dc, dr) => {
          const result = calcCancelDiff(ca, dc, dr)
          const expected = ca - dc - dr
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 外币折算 ───────────────────────────────────────────────────────────

describe('P5: 外币折算', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ amt, rate: calcFxConverted(amt, rate) === amt × rate
   * 折算本位币 = 原币回购额 × 回购日即期汇率
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

// ─── P6: 分类小计 ───────────────────────────────────────────────────────────

describe('P6: 分类小计', () => {
  /**
   * **Validates: Requirements 7.5**
   *
   * ∀ arr: calcSubtotal(arr) === Σarr
   * 分类小计 = 数组所有元素之和（按回购批次分类汇总）
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
