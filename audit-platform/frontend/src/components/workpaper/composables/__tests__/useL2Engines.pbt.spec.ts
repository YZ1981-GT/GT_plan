/**
 * Property-Based Tests — L2 应付利息公式引擎 + 计提核对引擎
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Tasks: 2.3 ~ 2.7
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P5。
 * 科目：2231 应付利息（贷方/负债类）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '../useL2FormulaEngine'
import {
  calcAccrualDiff,
  aggregateBySource,
  type InterestDetail,
} from '../useL2AccrualEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 安全浮点数生成器（避免NaN/Infinity/极端浮点精度问题） */
const arbSafeFloat = fc.integer({ min: -1_000_000_00, max: 1_000_000_00 }).map(n => n / 100)

/** 非负安全浮点（用于负债类期末P2：期初/贷方/借方均≥0） */
const arbNonNegFloat = fc.integer({ min: 0, max: 1_000_000_00 }).map(n => n / 100)

/** 来源类别生成器 */
const arbSource = fc.constantFrom(
  '短期借款利息',
  '长期借款利息',
  '应付债券利息',
  '融资租赁利息',
  '其他利息',
)

/** 应付利息明细行生成器 */
const arbInterestDetail: fc.Arbitrary<InterestDetail> = fc.record({
  source: arbSource,
  amount: arbSafeFloat,
})

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
      { numRuns: 200 },
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
   *
   * Generator: fc.float({min:0, max:1e9}) × 3（非负，代表实际借贷发生额）
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
      { numRuns: 200 },
    )
  })
})

// ─── P3: 计提差异 ──────────────────────────────────────────────────────────

describe('P3: 计提差异', () => {
  /**
   * **Validates: Requirements 4.4**
   *
   * ∀ est, booked: calcAccrualDiff(est, booked) === est - booked
   * 计提差异 = 测算利息 - 账面计提
   * 正值=账面少计提应补提，负值=账面多计提应冲回
   */
  it('calcAccrualDiff(est, booked) === est - booked', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        (est, booked) => {
          const result = calcAccrualDiff(est, booked)
          const expected = est - booked
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 小计求和 ──────────────────────────────────────────────────────────

describe('P4: 分类小计', () => {
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
        fc.array(arbSafeFloat, { minLength: 0, maxLength: 100 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 按来源汇总守恒 ────────────────────────────────────────────────────

describe('P5: 按来源汇总守恒', () => {
  /**
   * **Validates: Requirements 6.2**
   *
   * ∀ details (InterestDetail[]):
   *   Σ Object.values(aggregateBySource(details)) === Σ details.map(d => d.amount)
   * 分组汇总后各组之和必须等于全部明细之和（无遗漏无重复）
   */
  it('Σ aggregateBySource(details).values === Σ details.amount', () => {
    fc.assert(
      fc.property(
        fc.array(arbInterestDetail, { minLength: 0, maxLength: 100 }),
        (details) => {
          const grouped = aggregateBySource(details)
          const groupedSum = Object.values(grouped).reduce((a, b) => a + b, 0)
          const totalSum = details.reduce((a, d) => a + d.amount, 0)
          expect(groupedSum).toBeCloseTo(totalSum, 8)
        },
      ),
      { numRuns: 200 },
    )
  })
})
