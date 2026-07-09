/**
 * Property-Based Tests — L4 应付债券公式引擎 + 实际利率法引擎 + 权益划分引擎
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Tasks: 2.4 ~ 2.12
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P9。
 * 科目：2502 应付债券（贷方/负债类！）
 *
 * 🔴 实际利率法核心：利息费用=期初摊余成本×EIR；2分支付息；摊余成本终值趋面值
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcInitialAmount,
} from '../useL4FormulaEngine'
import {
  calcInterestExpense,
  calcEndAmortizedCost_Bullet,
  calcEndAmortizedCost_Installment,
  generateSchedule,
} from '../useL4EIREngine'
import {
  calcEquityComponent,
} from '../useL4EquityLiabEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 安全浮点数生成器（用整数/100避免浮点精度漂移） */
const arbSafeFloat = fc.integer({ min: -1_000_000_00, max: 1_000_000_00 }).map(n => n / 100)

/** 非负安全浮点 */
const arbNonNegFloat = fc.integer({ min: 0, max: 1_000_000_00 }).map(n => n / 100)

/** 摊余成本 (0, 10_000_000]（P3 专用） */
const arbAmortizedCost = fc.integer({ min: 1, max: 1_000_000_000 }).map(n => n / 100)

/** 实际利率 (0, 0.2)（P3 专用） */
const arbEIR = fc.integer({ min: 1, max: 2000 }).map(n => n / 10000)

/** 非负金额（用于bullet/installment） */
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
      { numRuns: 5 },
    )
  })
})

// ─── P2: 负债类期末余额（贷方！） ──────────────────────────────────────────

describe('P2: 负债类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, cr, dr: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额(发行/利息调整) - 借方发生额(兑付)
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
      { numRuns: 5 },
    )
  })
})

// ─── P3: 实际利率法利息费用 ─────────────────────────────────────────────────

describe('P3: 实际利率法利息费用', () => {
  /**
   * **Validates: Requirements 9.1**
   *
   * ∀ cost∈(0,10_000_000), eir∈(0,0.2):
   *   calcInterestExpense(cost, eir) === cost × eir
   * 利息费用 = 期初摊余成本 × 实际利率
   */
  it('calcInterestExpense(cost, eir) === cost × eir', () => {
    fc.assert(
      fc.property(
        arbAmortizedCost,
        arbEIR,
        (cost, eir) => {
          const result = calcInterestExpense(cost, eir)
          const expected = cost * eir
          expect(result).toBeCloseTo(expected, 6)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P4: 分支A摊余成本滚动（到期一次还本付息） ─────────────────────────────

describe('P4: 分支A摊余成本滚动', () => {
  /**
   * **Validates: Requirements 9.2**
   *
   * ∀ begin, ie: calcEndAmortizedCost_Bullet(begin, ie) === begin + ie
   * 到期一次还本付息：期末摊余成本 = 期初 + 利息费用（利息资本化滚入）
   */
  it('calcEndAmortizedCost_Bullet(begin, ie) === begin + ie', () => {
    fc.assert(
      fc.property(
        arbPositiveAmount,
        arbPositiveAmount,
        (begin, ie) => {
          const result = calcEndAmortizedCost_Bullet(begin, ie)
          const expected = begin + ie
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P5: 分支B摊余成本滚动（分期付息到期一次还本） ─────────────────────────

describe('P5: 分支B摊余成本滚动', () => {
  /**
   * **Validates: Requirements 9.3**
   *
   * ∀ begin, ie, cp: calcEndAmortizedCost_Installment(begin, ie, cp) === begin + ie - cp
   * 分期付息：期末摊余成本 = 期初 + 利息费用 - 实付票面利息
   */
  it('calcEndAmortizedCost_Installment(begin, ie, cp) === begin + ie - cp', () => {
    fc.assert(
      fc.property(
        arbPositiveAmount,
        arbPositiveAmount,
        arbPositiveAmount,
        (begin, ie, cp) => {
          const result = calcEndAmortizedCost_Installment(begin, ie, cp)
          const expected = begin + ie - cp
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P6: 摊余成本终值趋面值（installment分支） ─────────────────────────────

describe('P6: 摊余成本终值趋面值', () => {
  /**
   * **Validates: Requirements 9.5**
   *
   * ∀ self-consistent inputs (installment branch):
   *   |generateSchedule(...).last.endCost - faceValue| < 1
   * 分期付息分支下，最后一期期末摊余成本强制调整为面值（允许±1元尾差）
   */
  it('|generateSchedule(...).last.endCost - faceValue| < 1', () => {
    // 自洽生成器：initialCost > 0, faceValue > 0, couponRate ∈ (0, 0.15),
    // eir ∈ (0.001, 0.2), periods ∈ [1, 30], initialCost != faceValue
    const arbScheduleInputs = fc.tuple(
      fc.integer({ min: 100_000, max: 10_000_000 }),   // initialCost (分)
      fc.integer({ min: 100_000, max: 10_000_000 }),   // faceValue (分)
      fc.integer({ min: 1, max: 1500 }),               // couponRate (万分之)
      fc.integer({ min: 10, max: 2000 }),              // eir (万分之)
      fc.integer({ min: 1, max: 30 }),                 // periods
    ).filter(([ic, fv]) => ic !== fv) // 确保有实际摊销
      .map(([ic, fv, cr, eir, p]) => ({
        initialCost: ic / 100,
        faceValue: fv / 100,
        couponRate: cr / 10000,
        eir: eir / 10000,
        periods: p,
      }))

    fc.assert(
      fc.property(
        arbScheduleInputs,
        ({ initialCost, faceValue, couponRate, eir, periods }) => {
          const schedule = generateSchedule(
            initialCost, faceValue, couponRate, eir, periods, 'installment',
          )
          expect(schedule.length).toBe(periods)
          const lastRow = schedule[schedule.length - 1]
          expect(Math.abs(lastRow.endCost - faceValue)).toBeLessThan(1)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P7: 零利率利息恒等 ─────────────────────────────────────────────────────

describe('P7: 零利率利息恒等', () => {
  /**
   * **Validates: Requirements 9.6**
   *
   * ∀ cost: calcInterestExpense(cost, 0) === 0
   * EIR=0 时利息费用恒为 0（不产生 NaN，零息债券场景）
   */
  it('calcInterestExpense(cost, 0) === 0', () => {
    fc.assert(
      fc.property(
        arbAmortizedCost,
        (cost) => {
          expect(calcInterestExpense(cost, 0)).toBe(0)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P8: 初始入账金额 ──────────────────────────────────────────────────────

describe('P8: 初始入账金额', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * ∀ issue, cost: calcInitialAmount(issue, cost) === issue - cost
   * 初始入账金额 = 发行价格 - 交易费用
   */
  it('calcInitialAmount(issue, cost) === issue - cost', () => {
    fc.assert(
      fc.property(
        arbPositiveAmount,
        arbNonNegFloat,
        (issue, cost) => {
          const result = calcInitialAmount(issue, cost)
          const expected = issue - cost
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P9: 权益成分分拆 ──────────────────────────────────────────────────────

describe('P9: 权益成分分拆', () => {
  /**
   * **Validates: Requirements 10.2**
   *
   * ∀ total, liab: calcEquityComponent(total, liab) === total - liab
   * 权益成分 = 发行总额 - 负债成分（剩余法）
   */
  it('calcEquityComponent(total, liab) === total - liab', () => {
    fc.assert(
      fc.property(
        arbPositiveAmount,
        arbPositiveAmount,
        (total, liab) => {
          const result = calcEquityComponent(total, liab)
          const expected = total - liab
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 5 },
    )
  })
})
