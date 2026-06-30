/**
 * useD6FormulaEngine PBT
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D6 合同资产公式引擎核心纯函数。
 *
 * Spec: .kiro/specs/d6-contract-assets/
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcEndUnadjustedDebit,
  calcAuditedAmount,
  calcNetValue,
  calcBlockTotal,
  calcSubtotal,
  isChangeRateExceeding,
} from '../composables/useD6FormulaEngine'

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD6FormulaEngine - Property-Based Tests', () => {
  /**
   * **Feature: d6-contract-assets, Property 1: 借方科目期末余额公式**
   *
   * For any 期初审定余额(priorAudited≥0)、借方发生额(debit≥0)和贷方发生额(credit≥0)，
   * calcEndUnadjustedDebit(priorAudited, debit, credit) 的返回值应等于
   * priorAudited + debit - credit。借方科目核心公式。
   *
   * **Validates: Requirements 1.4, 5.4**
   */
  describe('Property 1: 借方科目期末余额公式', () => {
    it('calcEndUnadjustedDebit(priorAudited, debit, credit) === priorAudited + debit - credit', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          (priorAudited, debit, credit) => {
            const result = calcEndUnadjustedDebit(priorAudited, debit, credit)
            const expected = priorAudited + debit - credit
            expect(Math.abs(result - expected)).toBeLessThan(1e-6)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d6-contract-assets, Property 2: 审定数 = 未审 + AJE + RJE**
   *
   * For any 三元组 (未审数, AJE净额, RJE净额)，其中各值为有限数值，
   * calcAuditedAmount(unadjusted, aje, rje) 的返回值应等于 未审数 + AJE + RJE。
   * 适用于D6-1/D6-2/D6-3所有审定列。
   *
   * **Validates: Requirements 1.4, 2.3**
   */
  describe('Property 2: 审定数 = 未审 + AJE + RJE', () => {
    it('calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          (u, a, r) => {
            const result = calcAuditedAmount(u, a, r)
            const expected = u + a + r
            expect(Math.abs(result - expected)).toBeLessThan(1e-6)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d6-contract-assets, Property 3: 净值 = 原值 - 坏账准备（跨区块联动）**
   *
   * For any 原值审定数(originalValue≥0)和坏账准备审定数(impairment, 0≤impairment≤originalValue)，
   * calcNetValue(originalValue, impairment) 应等于 originalValue - impairment。
   * 此公式适用于三区块中所有对应行（动态行、小计行、非流动扣减行、区块合计行）。
   *
   * **Validates: Requirements 2.5, 3.3, 26.1, 26.2, 26.3**
   */
  describe('Property 3: 净值 = 原值 - 坏账准备（跨区块联动）', () => {
    it('calcNetValue(originalValue, impairment) === originalValue - impairment', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
          (originalValue, ratio) => {
            // impairment 约束: 0 ≤ impairment ≤ originalValue (via ratio scaling)
            const impairment = originalValue * ratio
            const result = calcNetValue(originalValue, impairment)
            const expected = originalValue - impairment
            expect(Math.abs(result - expected)).toBeLessThan(1e-6)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d6-contract-assets, Property 4: XX小计 = 小计 - 非流动扣减**
   *
   * For any (小计, "减：列示于其他非流动资产"扣减值) 对，
   * calcBlockTotal(subtotal, deduction) 应等于 subtotal - deduction。
   * 此为三个区块共有的"XX小计"计算逻辑。
   *
   * **Validates: Requirements 2.4, 26.4**
   */
  describe('Property 4: XX小计 = 小计 - 非流动扣减', () => {
    it('calcBlockTotal(subtotal, deduction) === subtotal - deduction', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
          (subtotal, ratio) => {
            // deduction 约束: 0 ≤ deduction ≤ subtotal (via ratio scaling)
            const deduction = subtotal * ratio
            const result = calcBlockTotal(subtotal, deduction)
            const expected = subtotal - deduction
            expect(Math.abs(result - expected)).toBeLessThan(1e-6)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d6-contract-assets, Property 6: 合计行 = SUM(明细行)**
   *
   * For any 数值数组（明细行的某个金额列），calcSubtotal(values) 应等于
   * values.reduce((a,b) => a+b, 0)。适用于D6-1各区块小计/D6-2合计/D6-3小计/D6-5合计/D6-8合计。
   *
   * **Validates: Requirements 2.4, 5.5, 8.4, 13.7**
   */
  describe('Property 6: 合计行 = SUM(明细行)', () => {
    it('calcSubtotal(arr) === arr.reduce((a,b) => a+b, 0)', () => {
      fc.assert(
        fc.property(
          fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 50 }),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((a, b) => a + b, 0)
            expect(Math.abs(result - expected)).toBeLessThan(1e-6)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d6-contract-assets, Property 9: 变动率阈值高亮判定**
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
          fc.float({ min: -10, max: 10, noNaN: true, noDefaultInfinity: true }),
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
