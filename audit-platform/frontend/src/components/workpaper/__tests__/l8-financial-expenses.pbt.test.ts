/**
 * Property-Based Tests — L8 财务费用公式引擎 + 利息引擎
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Tasks: 2.4 ~ 2.10
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1 ~ P7。
 * 科目：6603 财务费用（**借方/损益类！取发生额**）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcOccurrence,
  calcNetFinanceExpense,
  calcChangeRate,
} from '../composables/useL8FormulaEngine'
import {
  aggregateInterest,
  calcDeductibleInterest,
  calcExcessInterest,
} from '../composables/useL8InterestEngine'

// ─── 生成器 ─────────────────────────────────────────────────────────────────

const safeFloat = fc.float({ noNaN: true, noDefaultInfinity: true, min: -1e9, max: 1e9 })
const nonNegFloat = fc.float({ noNaN: true, noDefaultInfinity: true, min: 0, max: 1e9 })
const nonZeroFloat = fc.float({ noNaN: true, noDefaultInfinity: true, min: -1e9, max: 1e9 }).filter(x => x !== 0)
const principalFloat = fc.float({ noNaN: true, noDefaultInfinity: true, min: Math.fround(0.01), max: 1e9 })
const rateFloat = fc.float({ noNaN: true, noDefaultInfinity: true, min: Math.fround(0.001), max: Math.fround(0.2) })
const daysInt = fc.integer({ min: 0, max: 365 })

// ─── L8 Financial Expenses PBT ──────────────────────────────────────────────

describe('L8 Financial Expenses PBT', () => {
  // ─── P1: 审定数公式链 ─────────────────────────────────────────────────────

  describe('P1: 审定数公式链', () => {
    /**
     * **Validates: Requirements 8.1**
     *
     * ∀ u, a, r: calcAuditedAmount(u, a, r) === u + a + r
     * 审定数 = 未审数 + AJE + RJE
     */
    it('calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(
          safeFloat,
          safeFloat,
          safeFloat,
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

  // ─── P2: 损益类发生额（借-贷！） ─────────────────────────────────────────

  describe('P2: 损益类发生额（借-贷）', () => {
    /**
     * **Validates: Requirements 8.2**
     *
     * ∀ dr≥0, cr≥0: calcOccurrence(dr, cr) === dr - cr
     * 损益类本期发生额 = 借方发生 - 贷方发生（费用为借方科目）
     */
    it('calcOccurrence(dr, cr) === dr - cr', () => {
      fc.assert(
        fc.property(
          nonNegFloat,
          nonNegFloat,
          (dr, cr) => {
            const result = calcOccurrence(dr, cr)
            const expected = dr - cr
            expect(result).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  // ─── P3: 净财务费用 ───────────────────────────────────────────────────────

  describe('P3: 净财务费用', () => {
    /**
     * **Validates: Requirements 8.3**
     *
     * ∀ ie, ii, fx, fee, o: calcNetFinanceExpense(ie, ii, fx, fee, o) === ie - ii + fx + fee + o
     * 净财务费用 = 利息支出 - 利息收入 + 汇兑损益 + 手续费 + 其他
     */
    it('calcNetFinanceExpense(ie, ii, fx, fee, o) === ie - ii + fx + fee + o', () => {
      fc.assert(
        fc.property(
          safeFloat,
          safeFloat,
          safeFloat,
          safeFloat,
          safeFloat,
          (ie, ii, fx, fee, o) => {
            const result = calcNetFinanceExpense(ie, ii, fx, fee, o)
            const expected = ie - ii + fx + fee + o
            expect(result).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  // ─── P4: 变动率 ───────────────────────────────────────────────────────────

  describe('P4: 变动率', () => {
    /**
     * **Validates: Requirements 8.4**
     *
     * ∀ cur, prior(≠0): calcChangeRate(cur, prior) === (cur - prior) / prior × 100
     */
    it('calcChangeRate(cur, prior) === (cur - prior) / prior × 100 when prior ≠ 0', () => {
      fc.assert(
        fc.property(
          safeFloat,
          nonZeroFloat,
          (cur, prior) => {
            const result = calcChangeRate(cur, prior)
            const expected = ((cur - prior) / prior) * 100
            expect(result).toBeCloseTo(expected as number, 5)
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  // ─── P5: 利息汇总 ────────────────────────────────────────────────────────

  describe('P5: 利息来源汇总', () => {
    /**
     * **Validates: Requirements 8.5**
     *
     * ∀ l1, l3, l4, l5: aggregateInterest(l1, l3, l4, l5) === l1 + l3 + l4 + l5
     * 汇总L筹资循环全部利息来源
     */
    it('aggregateInterest(l1, l3, l4, l5) === l1 + l3 + l4 + l5', () => {
      fc.assert(
        fc.property(
          safeFloat,
          safeFloat,
          safeFloat,
          safeFloat,
          (l1, l3, l4, l5) => {
            const result = aggregateInterest(l1, l3, l4, l5)
            const expected = l1 + l3 + l4 + l5
            expect(result).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  // ─── P6: 可扣除利息 ───────────────────────────────────────────────────────

  describe('P6: 可扣除利息', () => {
    /**
     * **Validates: Requirements 8.5**
     *
     * ∀ p>0, rate∈(0,0.2), days∈[0,365]:
     *   calcDeductibleInterest(p, rate, days) === p × rate × days / 360
     * 非金融机构借款利息税前扣除限额（360天制）
     */
    it('calcDeductibleInterest(p, rate, days) === p × rate × days / 360', () => {
      fc.assert(
        fc.property(
          principalFloat,
          rateFloat,
          daysInt,
          (p, rate, days) => {
            const result = calcDeductibleInterest(p, rate, days)
            const expected = (p * rate * days) / 360
            expect(result).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 100 },
      )
    })
  })

  // ─── P7: 超标利息 ────────────────────────────────────────────────────────

  describe('P7: 超标利息', () => {
    /**
     * **Validates: Requirements 8.6**
     *
     * ∀ booked, deductible: calcExcessInterest(booked, deductible) === booked - deductible
     * 超标利息 = 账载利息 - 可扣除利息
     */
    it('calcExcessInterest(booked, deductible) === booked - deductible', () => {
      fc.assert(
        fc.property(
          safeFloat,
          safeFloat,
          (booked, deductible) => {
            const result = calcExcessInterest(booked, deductible)
            const expected = booked - deductible
            expect(result).toBeCloseTo(expected, 5)
          },
        ),
        { numRuns: 100 },
      )
    })
  })
})
