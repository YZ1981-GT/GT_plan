/**
 * Property-Based Tests — N3 递延所得税负债公式引擎 (P1~P5)
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Tasks: 2.3, 2.4, 2.5, 2.6, 2.7
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P5。
 * 科目：2901 递延所得税负债（贷方/负债类科目）
 *
 * P1: 审定数公式链 — calcAuditedAmount(u,a,r) === u+a+r
 * P2: 负债类期末余额 — calcLiabilityEndBalance(b,c,d) === b+c-d
 * P3: 应纳税暂时性差异 — calcTaxableTemporaryDifference(bv,tb) === bv-tb
 * P4: 递延税负债=差异×税率 — calcDeferredTaxLiability(diff,rate) === diff×rate
 * P5: 合计行恒等 — calcSubtotal(arr) === Σarr
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcAuditedAmount, calcLiabilityEndBalance, calcSubtotal } from '../composables/useN3FormulaEngine'
import { calcTaxableTemporaryDifference, calcDeferredTaxLiability } from '../composables/useN3DeferredTaxEngine'

// ─── Helper: 浮点容差比较 ───────────────────────────────────────────────────

/**
 * 浮点数相等判定（绝对容差 + 相对容差）
 * 绝对容差 1e-9，相对容差 1e-9
 */
function numericEquals(actual: number, expected: number): boolean {
  const absDiff = Math.abs(actual - expected)
  if (absDiff <= 1e-9) return true
  const relDiff = absDiff / Math.max(Math.abs(actual), Math.abs(expected), 1)
  return relDiff <= 1e-9
}

// ─── P1: 审定数公式链 ───────────────────────────────────────────────────────

describe('P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * ∀ u, a, r ∈ [-1e9, 1e9]:
   *   calcAuditedAmount(u, a, r) === u + a + r
   *
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
          expect(numericEquals(result, expected)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P2: 负债类期末余额（期初+贷-借） ──────────────────────────────────────

describe('P2: 负债类期末余额（期初+贷-借）', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, c, d ∈ [0, 1e9]:
   *   calcLiabilityEndBalance(b, c, d) === b + c - d
   *
   * 负债类（贷方科目）期末余额 = 期初 + 贷方发生额（确认） - 借方发生额（转回）
   * 2901递延所得税负债：贷增借减
   */
  it('calcLiabilityEndBalance(b, c, d) === b + c - d', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, c, d) => {
          const result = calcLiabilityEndBalance(b, c, d)
          const expected = b + c - d
          expect(numericEquals(result, expected)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P3: 应纳税暂时性差异（账面-计税基础） ─────────────────────────────────

describe('P3: 应纳税暂时性差异', () => {
  /**
   * **Validates: Requirements 3.2**
   *
   * ∀ bv, tb ∈ [-1e9, 1e9]:
   *   calcTaxableTemporaryDifference(bv, tb) === bv - tb
   *
   * 应纳税暂时性差异 = 账面价值 - 计税基础
   */
  it('calcTaxableTemporaryDifference(bv, tb) === bv - tb', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (bv, tb) => {
          const result = calcTaxableTemporaryDifference(bv, tb)
          const expected = bv - tb
          expect(numericEquals(result, expected)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 递延税负债=应纳税差异×税率 ────────────────────────────────────────

describe('P4: 递延税负债=应纳税差异×税率', () => {
  /**
   * **Validates: Requirements 4.1**
   *
   * ∀ diff ∈ [-1e9, 1e9], rate ∈ [0, 0.25]:
   *   calcDeferredTaxLiability(diff, rate) === diff × rate
   *
   * 递延所得税负债 = 应纳税暂时性差异 × 适用税率
   */
  it('calcDeferredTaxLiability(diff, rate) === diff × rate', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 0.25, noNaN: true }),
        (diff, rate) => {
          const result = calcDeferredTaxLiability(diff, rate)
          const expected = diff * rate
          expect(numericEquals(result, expected)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 合计行恒等 ────────────────────────────────────────────────────────

describe('P5: 合计行恒等', () => {
  /**
   * **Validates: Requirements 1.5**
   *
   * ∀ arr: number[]:
   *   calcSubtotal(arr) === arr.reduce((s, x) => s + x, 0)
   *
   * 合计行 = 数组各元素之和
   */
  it('calcSubtotal(arr) === arr.reduce((s, x) => s + x, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 20 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(numericEquals(result, expected)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })
})
