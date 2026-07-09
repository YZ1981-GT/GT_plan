/**
 * Property-Based Tests — M2 实收资本（股本）公式引擎（P1~P7）
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Tasks: 2.3 ~ 2.9
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P7。
 * 科目：4001 实收资本/股本（**贷方/权益类！**）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM2FormulaEngine'
import {
  calcFxConverted,
  calcFxDiff,
} from '../composables/useM2FxEngine'
import {
  calcVerifyDiff,
  calcPaidInRate,
} from '../composables/useM2VerifyEngine'

// ─── useM2FormulaEngine ─────────────────────────────────────────────────────

describe('useM2FormulaEngine', () => {
  // ─── P1: 审定数公式链 ─────────────────────────────────────────────────────

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

  // ─── P2: 权益类期末（贷方！） ─────────────────────────────────────────────

  describe('P2: 权益类贷方期末余额', () => {
    /**
     * **Validates: Requirements 2.4**
     *
     * ∀ b, cr, dr: calcEquityEndBalance(b, cr, dr) === b + cr - dr
     * 权益类（贷方科目）期末余额 = 期初 + 贷方发生额(增资) - 借方发生额(减资)
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

  // ─── P7: 小计求和 ─────────────────────────────────────────────────────────

  describe('P7: 分类小计', () => {
    /**
     * **Validates: Requirements 7.5**
     *
     * ∀ arr: calcSubtotal(arr) === Σarr
     * 分类小计 = 数组所有元素之和
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
})

// ─── useM2FxEngine ──────────────────────────────────────────────────────────

describe('useM2FxEngine', () => {
  // ─── P3: 外币折算 ─────────────────────────────────────────────────────────

  describe('P3: 外币投资折算', () => {
    /**
     * **Validates: Requirements 4.2**
     *
     * ∀ amt, rate: calcFxConverted(amt, rate) === amt × rate
     * 折算本位币 = 原币金额 × 出资日汇率
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

  // ─── P4: 折算差异 ─────────────────────────────────────────────────────────

  describe('P4: 折算差异', () => {
    /**
     * **Validates: Requirements 4.3**
     *
     * ∀ conv, booked: calcFxDiff(conv, booked) === conv - booked
     * 折算差异 = 折算本位币 - 账面本位币
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
})

// ─── useM2VerifyEngine ──────────────────────────────────────────────────────

describe('useM2VerifyEngine', () => {
  // ─── P5: 验资差异 ─────────────────────────────────────────────────────────

  describe('P5: 验资差异', () => {
    /**
     * **Validates: Requirements 5.2**
     *
     * ∀ paid, verified: calcVerifyDiff(paid, verified) === paid - verified
     * 验资差异 = 实缴出资 - 验资金额
     */
    it('calcVerifyDiff(paid, verified) === paid - verified', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (paid, verified) => {
            const result = calcVerifyDiff(paid, verified)
            const expected = paid - verified
            expect(result).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 200 },
      )
    })
  })

  // ─── P6: 出资到位率 ───────────────────────────────────────────────────────

  describe('P6: 出资到位率', () => {
    /**
     * **Validates: Requirements 5.3**
     *
     * ∀ paid, sub(sub≠0): calcPaidInRate(paid, sub) === paid / sub
     * 出资到位率 = 实缴出资 / 认缴出资
     */
    it('calcPaidInRate(paid, sub) === paid / sub (subscribed≠0)', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: Math.fround(0.01), max: 1e9, noNaN: true }),
          (paid, sub) => {
            const result = calcPaidInRate(paid, sub)
            const expected = paid / sub
            expect(result).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 200 },
      )
    })
  })
})
