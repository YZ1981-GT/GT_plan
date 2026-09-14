/**
 * Property-Based Tests — M6 未分配利润公式引擎 + 分配结转引擎（P1~P7）
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Tasks: 2.3 ~ 2.9
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5, P6, P7。
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！**）
 *
 * 核心公式链：期末未分配利润 = 期初 + 本年净利润 - 提取盈余公积 - 分配股利
 * 权益类贷方方向：期末 = 期初 + 贷方(增加) - 借方(减少)
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM6FormulaEngine'
import {
  calcRetainedEnd,
  calcDistributable,
  calcLinkageDiff,
} from '../composables/useM6DistributionEngine'

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
   * 权益类（贷方科目）期末余额 = 期初 + 贷方发生额(增加) - 借方发生额(减少)
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

// ─── P3: 利润分配结转核心公式链 ─────────────────────────────────────────────

describe('P3: 利润分配结转核心公式链', () => {
  /**
   * **Validates: Requirements 3.2**
   *
   * ∀ b, np, sa, d: calcRetainedEnd(b, np, sa, d) === b + np - sa - d
   * 期末未分配利润 = 期初 + 本年净利润 - 提取盈余公积 - 分配股利
   */
  it('calcRetainedEnd(b, np, sa, d) === b + np - sa - d', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (b, np, sa, d) => {
          const result = calcRetainedEnd(b, np, sa, d)
          const expected = b + np - sa - d
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 可供分配利润 ───────────────────────────────────────────────────────

describe('P4: 可供分配利润', () => {
  /**
   * **Validates: Requirements 4.5**
   *
   * ∀ b, np: calcDistributable(b, np) === b + np
   * 可供分配利润 = 期初未分配利润 + 本年净利润
   */
  it('calcDistributable(b, np) === b + np', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (b, np) => {
          const result = calcDistributable(b, np)
          const expected = b + np
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 联动差异 ───────────────────────────────────────────────────────────

describe('P5: 联动差异', () => {
  /**
   * **Validates: Requirements 6.1**
   *
   * ∀ m6, src: calcLinkageDiff(m6, src) === m6 - src
   * 联动差异 = M6值 - 来源值（差异=0表一致，≠0需核对）
   */
  it('calcLinkageDiff(m6, src) === m6 - src', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (m6, src) => {
          const result = calcLinkageDiff(m6, src)
          const expected = m6 - src
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
   * **Validates: Requirements 6.4**
   *
   * ∀ arr: calcSubtotal(arr) === Σarr
   * 分类小计 = 数组所有元素之和（利润分配项目分类汇总）
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

// ─── P7: 结转公式链一致性 ───────────────────────────────────────────────────

describe('P7: 结转公式链一致性', () => {
  /**
   * **Validates: Requirements 3.2, 4.5**
   *
   * ∀ b, np, sa, d: calcRetainedEnd(b, np, sa, d) === calcDistributable(b, np) - sa - d
   * 期末未分配利润 = 可供分配利润 - 提取盈余公积 - 分配股利
   * 等价性保证公式链逻辑闭环
   */
  it('calcRetainedEnd(b, np, sa, d) === calcDistributable(b, np) - sa - d', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (b, np, sa, d) => {
          const retained = calcRetainedEnd(b, np, sa, d)
          const distributable = calcDistributable(b, np)
          const expected = distributable - sa - d
          expect(retained).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
