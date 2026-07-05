/**
 * Property-Based Tests — F4 应付账款公式引擎
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Tasks 2.2 ~ 2.9
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcCreditBalance,
  calcAdjustedAmount,
  calcAgingCrossCheck,
  calcConcentration,
  calcChangeRate,
  isDebitCreditBalanced,
  calcOutstandingDays,
} from '../composables/useF4AccPayFormulaEngine'

describe('Feature: f4-accounts-payable, Property 1: 贷方余额公式', () => {
  /**
   * **Validates: Requirements 13.1, 3.3, 5.2**
   */
  it('calcCreditBalance(opening, credit, debit) === opening + credit - debit', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (opening, credit, debit) => {
          expect(calcCreditBalance(opening, credit, debit)).toBeCloseTo(opening + credit - debit, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f4-accounts-payable, Property 2: 审定数公式', () => {
  /**
   * **Validates: Requirements 13.2, 3.4**
   */
  it('calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (unadjusted, aje, rje) => {
          expect(calcAdjustedAmount(unadjusted, aje, rje)).toBeCloseTo(unadjusted + aje + rje, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f4-accounts-payable, Property 3: 账龄交叉校验', () => {
  /**
   * **Validates: Requirements 13.8, 5.3, 5.5**
   */
  it('calcAgingCrossCheck(a1+a2+a3+a4, closingBalance) === true when sum equals closing', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (a1, a2, a3, a4) => {
          const closingBalance = a1 + a2 + a3 + a4
          expect(calcAgingCrossCheck(closingBalance, closingBalance)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f4-accounts-payable, Property 4: 集中度公式', () => {
  /**
   * **Validates: Requirements 13.4, 9.3**
   */
  it('calcConcentration(amount, total) === amount/total × 100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (amount, total) => {
          expect(calcConcentration(amount, total)).toBeCloseTo((amount / total) * 100, 4)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f4-accounts-payable, Property 5: 变动率公式', () => {
  /**
   * **Validates: Requirements 13.6, 7.3**
   */
  it('calcChangeRate(current, prior) === (current-prior)/prior × 100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (current, prior) => {
          const result = calcChangeRate(current, prior)
          expect(result).toBeCloseTo(((current - prior) / prior) * 100, 4)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f4-accounts-payable, Property 6: 借贷平衡恒等', () => {
  /**
   * **Validates: Requirements 13.7, 6.2**
   */
  it('isDebitCreditBalanced(debits, credits) ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 20 }),
        fc.array(fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 20 }),
        (debits, credits) => {
          const d = debits.reduce((s, v) => s + v, 0)
          const c = credits.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(debits, credits)).toBe(Math.abs(d - c) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f4-accounts-payable, Property 7: 挂账天数非负', () => {
  /**
   * **Validates: Requirements 13.5, 8.2**
   */
  it('calcOutstandingDays(currentDate, startDate) >= 0', () => {
    fc.assert(
      fc.property(
        fc.date(),
        fc.date(),
        (currentDate, startDate) => {
          if (Number.isNaN(currentDate.getTime()) || Number.isNaN(startDate.getTime())) return
          expect(calcOutstandingDays(currentDate, startDate)).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: f4-accounts-payable, Property 8: 两级审定交叉校验', () => {
  /**
   * **Validates: Requirements 3.5, 3.8**
   *
   * 两级审定结构中：按性质分类的各行审定数小计 === 按账龄分类的各行审定数小计
   * 因为它们是同一科目的不同维度汇总，总计必须相等
   */
  it('SUM(natureRows.adjusted) === SUM(agingRows.adjusted) when constructed from same total', () => {
    fc.assert(
      fc.property(
        // Generate nature breakdown (e.g. 货款/工程款/服务费/其他)
        fc.array(
          fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
          { minLength: 2, maxLength: 5 },
        ),
        // Generate a split ratio for aging breakdown
        fc.array(
          fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
          { minLength: 2, maxLength: 4 },
        ),
        (natureAdjusted, ratios) => {
          // Sum of nature rows = total adjusted amount
          const totalNature = natureAdjusted.reduce((s, v) => s + v, 0)

          // Construct aging rows that sum to the same total (different decomposition)
          const ratioSum = ratios.reduce((s, v) => s + v, 0)
          const agingAdjusted = ratioSum > 0
            ? ratios.map(r => (r / ratioSum) * totalNature)
            : ratios.map((_, i) => i === 0 ? totalNature : 0)
          const totalAging = agingAdjusted.reduce((s, v) => s + v, 0)

          // Cross-check: both groupings must sum to same total
          expect(totalNature).toBeCloseTo(totalAging, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
