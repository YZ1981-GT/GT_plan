/**
 * Property-Based Tests — L1 短期借款公式引擎 + 利息引擎
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Tasks: 2.3 ~ 2.10
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P8。
 * 科目：2001 短期借款（贷方/负债类）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcCreditDiff,
  calcPledgeRatio,
} from '../useL1FormulaEngine'
import {
  calcInterest,
  calcOverdueDays,
} from '../useL1InterestEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 安全浮点数生成器（避免NaN/Infinity/极端浮点精度问题） */
const arbSafeFloat = fc.integer({ min: -1_000_000_00, max: 1_000_000_00 }).map(n => n / 100)

/** 非负安全浮点 */
const arbNonNegFloat = fc.integer({ min: 0, max: 1_000_000_00 }).map(n => n / 100)

/** 正浮点（>0） */
const arbPositiveFloat = fc.integer({ min: 1, max: 1_000_000_00 }).map(n => n / 100)

/** 日期生成器 */
const arbDate = fc.date({ min: new Date('2020-01-01'), max: new Date('2026-12-31') })

// ─── P1: 审定数公式链 ───────────────────────────────────────────────────────

describe('P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * ∀ u, a, r: calcAuditedAmount(u, a, r) === u + a + r
   * 审定数 = 未审数 + 审计调整 + 重分类调整
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        arbSafeFloat,
        (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P2: 负债类期末余额（贷方！） ──────────────────────────────────────────

describe('P2: 负债类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, cr, dr: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额 - 借方发生额
   */
  it('calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        arbNonNegFloat,
        arbNonNegFloat,
        arbNonNegFloat,
        (b, cr, dr) => {
          const result = calcLiabilityEndBalance(b, cr, dr)
          const expected = b + cr - dr
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P3: 利息测算公式（365天制） ────────────────────────────────────────────

describe('P3: 利息测算公式', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ p>0, rate∈(0,0.2), days∈[1,365]:
   *   calcInterest(p, rate, days) === p × rate × days / 365
   */
  it('calcInterest(p, rate, days) === p × rate × days / 365', () => {
    fc.assert(
      fc.property(
        arbPositiveFloat,
        fc.integer({ min: 1, max: 200 }).map(n => n / 1000), // rate ∈ (0, 0.2]
        fc.integer({ min: 1, max: 365 }),                     // days ∈ [1, 365]
        (p, rate, days) => {
          const result = calcInterest(p, rate, days)
          const expected = p * rate * days / 365
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P4: 零天数/零利率利息为0 ───────────────────────────────────────────────

describe('P4: 利息边界恒等', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ p, rate, days:
   *   calcInterest(p, rate, 0) === 0
   *   calcInterest(p, 0, days) === 0
   */
  it('days=0时利息恒为0', () => {
    fc.assert(
      fc.property(
        arbPositiveFloat,
        fc.integer({ min: 1, max: 200 }).map(n => n / 1000),
        (p, rate) => {
          expect(calcInterest(p, rate, 0)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('rate=0时利息恒为0', () => {
    fc.assert(
      fc.property(
        arbPositiveFloat,
        fc.integer({ min: 1, max: 365 }),
        (p, days) => {
          expect(calcInterest(p, 0, days)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P5: 逾期天数 ──────────────────────────────────────────────────────────

describe('P5: 逾期天数计算', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * ∀ due, report (Date):
   *   calcOverdueDays(due, report) === (report - due) 的天数差
   */
  it('calcOverdueDays(due, report) === 日期差（可负）', () => {
    fc.assert(
      fc.property(
        arbDate,
        arbDate,
        (due, report) => {
          const result = calcOverdueDays(due, report)
          // 手动计算 UTC 天数差
          const dueMs = Date.UTC(due.getFullYear(), due.getMonth(), due.getDate())
          const reportMs = Date.UTC(report.getFullYear(), report.getMonth(), report.getDate())
          const expected = Math.round((reportMs - dueMs) / (1000 * 60 * 60 * 24))
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P6: 担保比例 ──────────────────────────────────────────────────────────

describe('P6: 担保比例', () => {
  /**
   * **Validates: Requirements 6.5**
   *
   * ∀ loan≥0, value>0:
   *   calcPledgeRatio(loan, value) === loan / value × 100
   */
  it('calcPledgeRatio(loan, value) === loan / value × 100', () => {
    fc.assert(
      fc.property(
        arbNonNegFloat,
        arbPositiveFloat, // value > 0
        (loan, value) => {
          const result = calcPledgeRatio(loan, value)
          const expected = (loan / value) * 100
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P7: 征信差异 ──────────────────────────────────────────────────────────

describe('P7: 征信差异', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * ∀ credit, book:
   *   calcCreditDiff(credit, book) === credit - book
   */
  it('calcCreditDiff(credit, book) === credit - book', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        (credit, book) => {
          const result = calcCreditDiff(credit, book)
          const expected = credit - book
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P8: 分类小计 ──────────────────────────────────────────────────────────

describe('P8: 分类小计', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ arr (number[]):
   *   calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0)
   */
  it('calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(arbSafeFloat, { minLength: 0, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 100 },
    )
  })
})
