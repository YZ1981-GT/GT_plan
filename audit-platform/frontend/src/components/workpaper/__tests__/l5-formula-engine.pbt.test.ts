/**
 * Property-Based Tests — L5 长期应付款公式引擎
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Tasks: 2.3 ~ 2.6
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4。
 * 科目：2701 长期应付款（贷方/负债类！）+ 未确认融资费用（借方/负债备抵类）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcContraLiabilityEndBalance,
  calcNetPayable,
} from '../composables/useL5FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 安全浮点数生成器（避免 NaN/Infinity） */
const arbSafeFloat = fc.float({ noNaN: true, noDefaultInfinity: true })

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

// ─── P2: 负债类贷方期末余额 ─────────────────────────────────────────────────

describe('P2: 负债类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, cr, dr: calcLiabilityEndBalance(b, cr, dr) === b + cr - dr
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额(新增应付) - 借方发生额(偿还)
   */
  it('calcLiabilityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        arbSafeFloat,
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

// ─── P3: 备抵类期末余额（未确认融资费用，借方！） ────────────────────────────

describe('P3: 备抵类期末余额', () => {
  /**
   * **Validates: Requirements 2.5**
   *
   * ∀ b, dr, cr: calcContraLiabilityEndBalance(b, dr, cr) === b + dr - cr
   * 备抵类（借方科目）期末余额 = 期初 + 借方发生额（新增未确认）- 贷方发生额（摊销冲减）
   */
  it('calcContraLiabilityEndBalance(b, dr, cr) === b + dr - cr', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        arbSafeFloat,
        (b, dr, cr) => {
          const result = calcContraLiabilityEndBalance(b, dr, cr)
          const expected = b + dr - cr
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 5 },
    )
  })
})

// ─── P4: 长期应付款净额 ─────────────────────────────────────────────────────

describe('P4: 长期应付款净额', () => {
  /**
   * **Validates: Requirements 2.6**
   *
   * ∀ payable, unrecognized:
   *   calcNetPayable(payable, unrecognized) === payable - unrecognized
   *
   * 净额 = 长期应付款余额（面值）- 未确认融资费用余额
   * 报表列报的长期应付款 = 面值 - 未确认融资费用 = 实际融资成本（现值）
   */
  it('calcNetPayable(payable, unrecognized) === payable - unrecognized', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        (payable, unrecognized) => {
          const result = calcNetPayable(payable, unrecognized)
          const expected = payable - unrecognized
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 5 },
    )
  })
})
