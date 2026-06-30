/**
 * Property-Based Tests — D1 审定表公式引擎
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Tasks: 1.2–1.7
 *
 * 使用 fast-check + vitest 验证 6 个 correctness properties。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcChangeRate,
  calcSubtotal,
  calcNetValue,
  isChangeRateExceeding,
  calcBadDebtEndBalance,
} from '../useD1FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 审定数公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 1: 审定数公式正确性', () => {
  /**
   * **Validates: Requirements 1.3, 4.5, 5.5, 6.3**
   *
   * 审定数 = 未审数 + AJE净额 + RJE净额
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (unadjusted, aje, rje) => {
          const result = calcAuditedAmount(unadjusted, aje, rje)
          const expected = unadjusted + aje + rje
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 变动额与变动率公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 2: 变动额与变动率公式正确性', () => {
  /**
   * **Validates: Requirements 1.4**
   *
   * 变动率三分支：prior=0&&audited=0→''; prior=0&&audited≠0→1; otherwise→(audited-prior)/prior
   */
  it('calcChangeRate follows three-branch logic with zero boundary', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          // Strategy 1: both zero
          fc.constant([0, 0] as [number, number]),
          // Strategy 2: prior=0, audited≠0
          fc.float({ noNaN: true }).filter(v => v !== 0).map(v => [0, v] as [number, number]),
          // Strategy 3: general case (prior≠0)
          fc.tuple(
            fc.float({ noNaN: true }).filter(v => v !== 0),
            fc.float({ noNaN: true }),
          ),
        ),
        ([prior, audited]) => {
          const result = calcChangeRate(prior, audited)

          if (prior === 0 && audited === 0) {
            expect(result).toBe('')
          } else if (prior === 0) {
            expect(result).toBe(1)
          } else {
            expect(result).toBeCloseTo((audited - prior) / prior, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 小计行恒等于明细行之和
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 3: 小计行恒等于明细行之和', () => {
  /**
   * **Validates: Requirements 1.5, 4.6, 5.6, 6.5**
   *
   * calcSubtotal(rows) === rows.reduce((a,b)=>a+b, 0)
   */
  it('calcSubtotal equals sum of all elements', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ noNaN: true }), { minLength: 1, maxLength: 20 }),
        (rows) => {
          const result = calcSubtotal(rows)
          const expected = rows.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 净值等于原值减坏账准备
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 4: 净值等于原值减坏账准备', () => {
  /**
   * **Validates: Requirements 1.6**
   *
   * calcNetValue(gross, bad) === gross - bad
   */
  it('calcNetValue(gross, bad) === gross - bad', () => {
    fc.assert(
      fc.property(
        fc.float({ noNaN: true }),
        fc.float({ noNaN: true }),
        (gross, bad) => {
          const result = calcNetValue(gross, bad)
          const expected = gross - bad
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 变动率阈值高亮判定
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 5: 变动率阈值高亮判定', () => {
  /**
   * **Validates: Requirements 1.7**
   *
   * isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)
   */
  it('isChangeRateExceeding correctly compares abs(rate) against threshold', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -10, max: 10, noNaN: true }),
        (rate) => {
          const result = isChangeRateExceeding(rate, 0.3)
          const expected = Math.abs(rate) > 0.3
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 11: 坏账准备期末未审数公式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 11: 坏账准备期末未审数公式', () => {
  /**
   * **Validates: Requirements 6.4**
   *
   * calcBadDebtEndBalance = 期初审定 + 计提 - 收回 - 转回 - 核销 + 其他
   */
  it('calcBadDebtEndBalance follows the formula: prior + provision - recovery - reversal - writeOff + other', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (priorAudited, provision, recovery, reversal, writeOff, other) => {
          const result = calcBadDebtEndBalance(priorAudited, provision, recovery, reversal, writeOff, other)
          const expected = priorAudited + provision - recovery - reversal - writeOff + other
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
