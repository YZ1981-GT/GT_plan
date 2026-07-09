/**
 * Property-Based Tests — L3 长期借款公式引擎 + 利息引擎 + 重分类引擎
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Tasks: 2.4 ~ 2.11
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P8。
 * 科目：2501 长期借款（贷方/负债类）
 *
 * 🔴 365天制（源模板确认：M11=J11*I11/365*L11）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcPledgeRatio,
} from '../useL3FormulaEngine'
import {
  calcInterest,
  calcOverdueDays,
} from '../useL3InterestEngine'
import {
  calcCurrentPortion,
} from '../useL3ReclassEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 安全浮点数生成器（用整数/100避免浮点精度漂移） */
const arbSafeFloat = fc.integer({ min: -1_000_000_00, max: 1_000_000_00 }).map(n => n / 100)

/** 非负安全浮点（负债类发生额） */
const arbNonNegFloat = fc.integer({ min: 0, max: 1_000_000_00 }).map(n => n / 100)

/** 正本金 */
const arbPrincipal = fc.integer({ min: 100, max: 1_000_000_00 }).map(n => n / 100)

/** 利率 (0, 0.2] */
const arbRate = fc.integer({ min: 1, max: 2000 }).map(n => n / 10000)

/** 计息天数 [1, 365] */
const arbDays = fc.integer({ min: 1, max: 365 })

/** 非负天数 [0, 365] */
const arbDaysOrZero = fc.integer({ min: 0, max: 365 })

/** 非负利率 [0, 0.2] */
const arbRateOrZero = fc.integer({ min: 0, max: 2000 }).map(n => n / 10000)

/** ISO日期生成器 (2000-2030范围，确保有效YYYY-MM-DD) */
const arbISODate = fc.tuple(
  fc.integer({ min: 2000, max: 2030 }),
  fc.integer({ min: 1, max: 12 }),
  fc.integer({ min: 1, max: 28 }), // 用28避免月末无效日
).map(([y, m, d]) => {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
})

/** 正金额 (担保/重分类) */
const arbPositiveAmount = fc.integer({ min: 1, max: 1_000_000_00 }).map(n => n / 100)

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
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额(借入) - 借方发生额(归还)
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

// ─── P3: 利息测算公式 ──────────────────────────────────────────────────────

describe('P3: 利息测算公式', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ p>0, rate∈(0,0.2], days∈[1,365]:
   *   calcInterest(p, rate, days) === p × rate × days / 365
   * 利息 = 本金 × 年利率 × 计息天数 / 365（365天制）
   */
  it('calcInterest(p, rate, days) === p * rate * days / 365', () => {
    fc.assert(
      fc.property(
        arbPrincipal,
        arbRate,
        arbDays,
        (p, rate, days) => {
          const result = calcInterest(p, rate, days)
          const expected = p * rate * days / 365
          expect(result).toBeCloseTo(expected, 6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P4: 利息边界恒等（零天数/零利率） ──────────────────────────────────────

describe('P4: 利息边界恒等', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ p, rate: calcInterest(p, rate, 0) === 0
   * ∀ p, days: calcInterest(p, 0, days) === 0
   * 零天数或零利率时利息恒为0
   */
  it('calcInterest(p, rate, 0) === 0（零天数）', () => {
    fc.assert(
      fc.property(
        arbNonNegFloat,
        arbRateOrZero,
        (p, rate) => {
          expect(calcInterest(p, rate, 0)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcInterest(p, 0, days) === 0（零利率）', () => {
    fc.assert(
      fc.property(
        arbNonNegFloat,
        arbDaysOrZero,
        (p, days) => {
          expect(calcInterest(p, 0, days)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P5: 逾期天数计算 ──────────────────────────────────────────────────────

describe('P5: 逾期天数计算', () => {
  /**
   * **Validates: Requirements 7.2**
   *
   * ∀ dueDate, reportDate (valid ISO dates):
   *   calcOverdueDays(due, report) === (report - due) in days
   * 逾期天数 = 报告日 - 到期日
   */
  it('calcOverdueDays(due, report) === 日期差(report - due)', () => {
    fc.assert(
      fc.property(
        arbISODate,
        arbISODate,
        (dueDate, reportDate) => {
          const result = calcOverdueDays(dueDate, reportDate)

          // 用同样逻辑手动计算日期差
          const dueParts = dueDate.split('-')
          const reportParts = reportDate.split('-')
          const dueMs = Date.UTC(
            parseInt(dueParts[0], 10),
            parseInt(dueParts[1], 10) - 1,
            parseInt(dueParts[2], 10),
          )
          const reportMs = Date.UTC(
            parseInt(reportParts[0], 10),
            parseInt(reportParts[1], 10) - 1,
            parseInt(reportParts[2], 10),
          )
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
   * **Validates: Requirements 6.2**
   *
   * ∀ loan≥0, value>0:
   *   calcPledgeRatio(loan, value) === loan / value × 100
   * 担保比例 = 担保借款额 / 资产账面价值 × 100
   */
  it('calcPledgeRatio(loan, value) === loan / value * 100', () => {
    fc.assert(
      fc.property(
        arbNonNegFloat,
        arbPositiveAmount,
        (loan, value) => {
          const result = calcPledgeRatio(loan, value)
          const expected = (loan / value) * 100
          expect(result).toBeCloseTo(expected, 6)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P7: 一年内到期重分类边界 ──────────────────────────────────────────────

describe('P7: 一年内到期重分类边界', () => {
  /**
   * **Validates: Requirements 5.1**
   *
   * ∀ dueDate > reportDate + 1年, amount > 0:
   *   calcCurrentPortion(due, report, amount) === 0
   * 到期日超过报告日一年以上时不需重分类
   */
  it('到期日>报告日+1年时 calcCurrentPortion === 0', () => {
    // 生成reportDate，然后生成dueDate保证 > reportDate + 1年
    const arbReportDate = fc.date({
      min: new Date('2000-01-01T00:00:00Z'),
      max: new Date('2028-12-31T00:00:00Z'),
    })

    fc.assert(
      fc.property(
        arbReportDate,
        fc.integer({ min: 2, max: 3650 }), // 额外天数（至少2天保证严格大于1年）
        arbPositiveAmount,
        (report, extraDays, amount) => {
          // reportDate ISO
          const ry = report.getFullYear()
          const rm = String(report.getMonth() + 1).padStart(2, '0')
          const rd = String(report.getDate()).padStart(2, '0')
          const reportStr = `${ry}-${rm}-${rd}`

          // dueDate = reportDate + 1年 + extraDays
          const dueDate = new Date(report.getTime())
          dueDate.setFullYear(dueDate.getFullYear() + 1)
          dueDate.setDate(dueDate.getDate() + extraDays)
          const dy = dueDate.getFullYear()
          const dm = String(dueDate.getMonth() + 1).padStart(2, '0')
          const dd = String(dueDate.getDate()).padStart(2, '0')
          const dueStr = `${dy}-${dm}-${dd}`

          const result = calcCurrentPortion(dueStr, reportStr, amount)
          expect(result).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P8: 分类小计 ──────────────────────────────────────────────────────────

describe('P8: 分类小计', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * ∀ arr (number[]):
   *   calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0)
   * 分类小计求和守恒
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
