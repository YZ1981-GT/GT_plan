/**
 * Property-Based Tests — M9 其他综合收益公式引擎 + OCI核对引擎（P1~P6）
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Tasks: 2.3 ~ 2.8
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5, P6。
 * 科目：4103 其他综合收益（**贷方/权益类！**）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M9其他综合收益（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：      期末 = 期初 + 借方 - 贷方
 *
 * OCI两大类：
 *   - nonReclass（不可重分类进损益）：G8其他权益工具投资公允变动、J2设定受益计划重计量
 *   - reclass（可重分类进损益）：其他债权投资公允变动、现金流量套期损益、外币折算差额
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM9FormulaEngine'
import {
  calcAfterTaxNet,
  calcReconcileDiff,
  aggregateOci,
} from '../composables/useM9OciEngine'
import type { OciItem } from '../composables/useM9OciEngine'

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
   * 权益类（贷方科目）期末余额 = 期初 + 贷方发生额(OCI增加) - 借方发生额(OCI减少/重分类)
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

// ─── P3: 税后净额 ───────────────────────────────────────────────────────────

describe('P3: OCI税后净额', () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * ∀ pre, tax: calcAfterTaxNet(pre, tax) === pre - tax
   * 税后净额 = 本期税前发生额 - 所得税影响额
   * 每项OCI按税后净额列示（CAS30要求）
   */
  it('calcAfterTaxNet(pre, tax) === pre - tax', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (pre, tax) => {
          const result = calcAfterTaxNet(pre, tax)
          const expected = pre - tax
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 核对差异 ───────────────────────────────────────────────────────────

describe('P4: 多来源核对差异', () => {
  /**
   * **Validates: Requirements 4.5**
   *
   * ∀ src, booked: calcReconcileDiff(src, booked) === src - booked
   * 核对差异 = 来源金额（G8/J2/外币等底稿税后净额） - 账面OCI增加
   * 差异为0=核对一致；非0=需要解释原因
   */
  it('calcReconcileDiff(src, booked) === src - booked', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (src, booked) => {
          const result = calcReconcileDiff(src, booked)
          const expected = src - booked
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: OCI两大类汇总 ──────────────────────────────────────────────────────

describe('P5: OCI两大类汇总', () => {
  /**
   * **Validates: Requirements 6.1-6.3**
   *
   * ∀ items: aggregateOci(items).total === aggregateOci(items).nonReclass + aggregateOci(items).reclass
   * OCI汇总 = 不可重分类合计 + 可重分类合计
   *
   * 不可重分类：G8其他权益工具投资公允变动、J2设定受益计划重计量
   * 可重分类：其他债权投资公允变动、现金流量套期损益、外币折算差额
   */
  it('aggregateOci(items).total === nonReclass + reclass', () => {
    const ociItemArb = fc.record({
      amount: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
      category: fc.constantFrom('nonReclass' as const, 'reclass' as const),
    })

    fc.assert(
      fc.property(
        fc.array(ociItemArb, { minLength: 0, maxLength: 50 }),
        (items: OciItem[]) => {
          const result = aggregateOci(items)
          expect(result.total).toBeCloseTo(result.nonReclass + result.reclass, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P6: 分类小计 ───────────────────────────────────────────────────────────

describe('P6: 分类小计', () => {
  /**
   * **Validates: Requirements 6.4**
   *
   * ∀ arr: calcSubtotal(arr) === Σarr
   * 分类小计 = 数组所有元素之和（OCI两大类各自汇总用）
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
