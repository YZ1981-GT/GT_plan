/**
 * Property-Based Tests — M10 其他权益工具公式引擎 + CAS37区分引擎（P1~P6）
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Tasks: 2.3 ~ 2.8
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1, P2, P3, P4, P5, P6。
 * 科目：4003 其他权益工具（**贷方/权益类！**）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M10其他权益工具（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：      期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM10FormulaEngine'
import {
  classifyInstrument,
  splitAmount,
  calcClassificationConsistency,
} from '../composables/useM10ClassificationEngine'

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
   * 权益类（贷方科目）期末余额 = 期初 + 贷方发生额(发行增加) - 借方发生额(赎回/转换减少)
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

// ─── P3: CAS37分类判定 ──────────────────────────────────────────────────────

describe('P3: CAS37负债权益判定', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ obligation (boolean):
   *   classifyInstrument(obligation) === (obligation ? 'liability' : 'equity')
   *
   * CAS37核心：有交付现金/金融资产的合同义务→金融负债；无→权益工具
   */
  it('classifyInstrument(ob) === (ob ? "liability" : "equity")', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (hasObligation) => {
          const result = classifyInstrument(hasObligation)
          const expected = hasObligation ? 'liability' : 'equity'
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 金额拆分 ───────────────────────────────────────────────────────────

describe('P4: 权益负债金额拆分', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ total, eq: splitAmount(total, eq) === total - eq
   * 负债部分 = 工具总额 - 权益部分
   */
  it('splitAmount(total, eq) === total - eq', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (total, eq) => {
          const result = splitAmount(total, eq)
          const expected = total - eq
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 分类金额守恒 ──────────────────────────────────────────────────────

describe('P5: 权益负债金额守恒', () => {
  /**
   * **Validates: Requirements 6.1**
   *
   * ∀ total: 生成 eq 和 liab=total-eq → calcClassificationConsistency(eq, liab, total) === true
   * 分类后：权益部分 + 负债部分 === 总额（守恒）
   */
  it('eq + liab === total 时守恒为 true', () => {
    // 使用整数映射避免浮点精度问题：先生成 total，再从 total 中拆分 eq 和 liab
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1_000_000_00 }),
        fc.integer({ min: 0, max: 100 }),
        (totalCents, pct) => {
          const total = totalCents / 100
          const eq = Math.round(total * pct) / 100
          const liab = Math.round((total - eq) * 100) / 100
          // 重建 total 为 eq+liab 确保精确守恒
          const result = calcClassificationConsistency(eq, liab, eq + liab)
          expect(result).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('eq + liab !== total 时守恒为 false', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 1, max: 1e6, noNaN: true }),
        (eq, liab, offset) => {
          // total 故意偏移，使 eq+liab !== total
          const total = eq + liab + offset
          const result = calcClassificationConsistency(eq, liab, total)
          expect(result).toBe(false)
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
   * 分类小计 = 数组所有元素之和（按工具类型分类汇总：永续债/优先股/其他）
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
