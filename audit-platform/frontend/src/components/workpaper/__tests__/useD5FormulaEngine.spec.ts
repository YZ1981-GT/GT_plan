/**
 * useD5FormulaEngine PBT + 单元测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D5 应收款项融资公式引擎全部纯函数。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcDiscountInterest,
  calcFairValue,
  calcRemainingDays,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
  calcFvTotal,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
  calcImpairmentEnd,
} from '../composables/useD5FormulaEngine'

// ─── 单元测试 ────────────────────────────────────────────────────────────────

describe('useD5FormulaEngine - 单元测试', () => {
  describe('parseNum', () => {
    it('returns 0 for null', () => expect(parseNum(null)).toBe(0))
    it('returns 0 for undefined', () => expect(parseNum(undefined)).toBe(0))
    it('returns 0 for empty string', () => expect(parseNum('')).toBe(0))
    it('returns 0 for NaN string', () => expect(parseNum('abc')).toBe(0))
    it('returns 0 for Infinity', () => {
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })
    it('parses numeric strings', () => expect(parseNum('123.45')).toBe(123.45))
    it('passes through numbers', () => expect(parseNum(42)).toBe(42))
    it('returns 0 for NaN number', () => expect(parseNum(NaN)).toBe(0))
  })

  describe('calcRemainingDays', () => {
    it('returns correct day difference', () => {
      expect(calcRemainingDays('2026-01-01', '2026-01-31')).toBe(30)
    })
    it('returns 0 for empty dates', () => {
      expect(calcRemainingDays('', '2026-01-31')).toBe(0)
      expect(calcRemainingDays('2026-01-01', '')).toBe(0)
    })
    it('returns 0 when maturity before measurement', () => {
      expect(calcRemainingDays('2026-06-30', '2026-01-01')).toBe(0)
    })
    it('returns 0 for invalid dates', () => {
      expect(calcRemainingDays('invalid', '2026-01-31')).toBe(0)
      expect(calcRemainingDays('2026-01-01', 'invalid')).toBe(0)
    })
    it('returns 0 when same date', () => {
      expect(calcRemainingDays('2026-06-30', '2026-06-30')).toBe(0)
    })
    it('handles cross-year dates', () => {
      // 2026-12-01 to 2027-03-01 = 90 days
      expect(calcRemainingDays('2026-12-01', '2027-03-01')).toBe(90)
    })
  })

  describe('calcChangeRate', () => {
    it('returns empty string when both 0', () => expect(calcChangeRate(0, 0)).toBe(''))
    it('returns N/A when prior=0 current≠0', () => expect(calcChangeRate(0, 100)).toBe('N/A'))
    it('calculates rate', () => expect(calcChangeRate(100, 120)).toBeCloseTo(0.2))
    it('handles negative change', () => expect(calcChangeRate(100, 80)).toBeCloseTo(-0.2))
  })

  describe('calcImpairmentEnd', () => {
    it('期末 = 上年末 + 计提 - 转回 - 核销', () => {
      expect(calcImpairmentEnd(1000, 200, 50, 30)).toBe(1120)
    })
    it('all zeros → 0', () => {
      expect(calcImpairmentEnd(0, 0, 0, 0)).toBe(0)
    })
  })

  describe('calcEndBalance (借方科目)', () => {
    it('期末 = 期初审定 + 增加 - 减少', () => {
      expect(calcEndBalance(1000, 500, 200)).toBe(1300)
    })
  })
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD5FormulaEngine - Property-Based Tests', () => {
  /**
   * **Feature: d5-receivables-financing, Property 1: 贴现利息公式正确性**
   *
   * For any 票面金额(face≥0)、市场贴现利率(rate∈[0,1])和剩余天数(days≥0)，
   * calcDiscountInterest(face, rate, days) 的返回值应等于 face × rate × days / 360。
   *
   * **Validates: Requirements 1.4, 6.2**
   */
  describe('Property 1: 贴现利息公式正确性', () => {
    it('calcDiscountInterest(face, rate, days) === face * rate * days / 360', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          fc.float({ min: 0, max: 1, noNaN: true }),
          fc.integer({ min: 0, max: 365 }),
          (face, rate, days) => {
            expect(calcDiscountInterest(face, rate, days)).toBeCloseTo(face * rate * days / 360, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d5-receivables-financing, Property 2: 公允价值 = 票面 - 贴现利息**
   *
   * For any 票面金额(face≥0)和贴现利息(interest≥0 且 interest≤face)，
   * calcFairValue(face, interest) 的返回值应等于 face - interest。
   *
   * **Validates: Requirements 1.4, 6.2**
   */
  describe('Property 2: 公允价值 = 票面 - 贴现利息', () => {
    it('calcFairValue(face, interest) === face - interest', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          (face, interest) => {
            expect(calcFairValue(face, interest)).toBeCloseTo(face - interest, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d5-receivables-financing, Property 3: 审定数 = 未审 + AJE + RJE**
   *
   * For any 三元组 (未审数, AJE净额, RJE净额)，其中各值为有限数值，
   * calcAuditedAmount 的返回值应等于 未审数 + AJE + RJE。
   *
   * **Validates: Requirements 1.4, 2.3**
   */
  describe('Property 3: 审定数 = 未审 + AJE + RJE', () => {
    it('calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (u, a, r) => {
            expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d5-receivables-financing, Property 4: 公允价值合计 = 小计 - OCI变动**
   *
   * For any (小计, OCI变动) 对，calcFvTotal(subtotal, ociChange) 应等于
   * subtotal - ociChange。此为D5审定表特殊结构的核心公式。
   *
   * **Validates: Requirements 2.4, 3.2**
   */
  describe('Property 4: 公允价值合计 = 小计 - OCI变动', () => {
    it('calcFvTotal(subtotal, oci) === subtotal - oci', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (subtotal, oci) => {
            expect(calcFvTotal(subtotal, oci)).toBeCloseTo(subtotal - oci, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d5-receivables-financing, Property 6: 合计行 = SUM(明细行)**
   *
   * For any 数值数组（明细行的某个金额列），calcSubtotal(values) 应等于
   * values.reduce((a,b) => a+b, 0)。适用于D5-1小计/D5-2合计/D5-4合计所有合计行。
   *
   * **Validates: Requirements 2.4, 4.4, 6.5**
   */
  describe('Property 6: 合计行 = SUM(明细行)', () => {
    it('calcSubtotal(arr) === arr.reduce((a,b) => a+b, 0)', () => {
      fc.assert(
        fc.property(
          fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true }), { minLength: 1, maxLength: 30 }),
          (arr) => {
            const expected = arr.reduce((a, b) => a + b, 0)
            expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d5-receivables-financing, Property 9: 变动率阈值高亮判定**
   *
   * For any 变动率数值 r（有限数值），isChangeRateExceeding(r, 0.3) 应返回 true
   * 当且仅当 |r| > 0.3。对于空串或'N/A'应返回false。
   *
   * **Validates: Requirements 2.7**
   */
  describe('Property 9: 变动率阈值高亮判定', () => {
    it('isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -10, max: 10, noNaN: true }),
          (r) => {
            expect(isChangeRateExceeding(r, 0.3)).toBe(Math.abs(r) > 0.3)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('returns false for empty string and N/A', () => {
      expect(isChangeRateExceeding('', 0.3)).toBe(false)
      expect(isChangeRateExceeding('N/A', 0.3)).toBe(false)
    })
  })
})
