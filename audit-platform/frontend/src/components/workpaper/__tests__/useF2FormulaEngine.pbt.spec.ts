/**
 * Property-Based Tests — F2 存货底稿核心组公式引擎
 *
 * Spec: .kiro/specs/f2-inventory-main/
 * Tasks: 2.2 ~ 2.10
 *
 * Property 1: 期末余额公式 (期末=期初+增加-减少)
 * Property 2: 净值=原值-跌价准备
 * Property 3: 审定数=未审+AJE
 * Property 4: 合计行=SUM(明细行)
 * Property 5: 库龄合计=Σ4段
 * Property 6: 单价=金额/数量
 * Property 7: 变动率边界处理
 * Property 8: 产销率公式
 * Property 9: 检查比例公式
 *
 * **Validates: Requirements 18.2~18.11, 2.3, 2.5, 5.3~5.7, 9.5, 12.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  calcEndBalance,
  calcNetValue,
  calcAuditedAmount,
  calcSubtotal,
  calcAgingTotal,
  calcUnitPrice,
  calcChangeRate,
  calcProductionSalesRate,
  calcCoverageRatio,
} from '../composables/useF2InvMaiFormulaEngine'

// ─── Property 1 PBT: 期末余额公式 ──────────────────────────────────────────

describe('Feature: f2-inventory-main, Property 1: 期末=期初+增加-减少', () => {
  /**
   * **Validates: Requirements 18.2, 5.3, 5.4**
   *
   * ∀ opening, increase, decrease ∈ ℝ:
   * calcEndBalance(opening, increase, decrease) === opening + increase - decrease
   */
  it('期末余额恒等于期初+增加-减少', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (opening, increase, decrease) => {
          const result = calcEndBalance(opening, increase, decrease)
          const expected = opening + increase - decrease
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 2 PBT: 净值=原值-跌价准备 ────────────────────────────────────

describe('Feature: f2-inventory-main, Property 2: 净值=原值-跌价准备', () => {
  /**
   * **Validates: Requirements 18.3, 2.5**
   *
   * ∀ originalValue, impairment ∈ ℝ≥0:
   * calcNetValue(originalValue, impairment) === originalValue - impairment
   */
  it('净值恒等于原值减去跌价准备', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (originalValue, impairment) => {
          const result = calcNetValue(originalValue, impairment)
          const expected = originalValue - impairment
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 3 PBT: 审定数=未审+AJE ───────────────────────────────────────

describe('Feature: f2-inventory-main, Property 3: 审定数=未审+AJE', () => {
  /**
   * **Validates: Requirements 18.4, 2.3**
   *
   * ∀ unadjusted, aje ∈ ℝ:
   * calcAuditedAmount(unadjusted, aje, 0) === unadjusted + aje
   * (RJE=0 for simplified two-arg scenario)
   */
  it('审定数恒等于未审数加审计调整', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (unadjusted, aje) => {
          const result = calcAuditedAmount(unadjusted, aje, 0)
          const expected = unadjusted + aje
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 4 PBT: 合计行=SUM(明细行) ────────────────────────────────────

describe('Feature: f2-inventory-main, Property 4: 合计行=SUM(明细行)', () => {
  /**
   * **Validates: Requirements 18.7, 5.6**
   *
   * ∀ arr: number[]:
   * calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
   */
  it('合计行恒等于所有明细行之和', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          { minLength: 1, maxLength: 50 },
        ),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 5 PBT: 库龄合计=Σ4段 ────────────────────────────────────────

describe('Feature: f2-inventory-main, Property 5: 库龄合计=Σ4段', () => {
  /**
   * **Validates: Requirements 18.6, 5.7**
   *
   * ∀ a,b,c,d ∈ ℝ≥0:
   * calcAgingTotal(a,b,c,d) === a+b+c+d
   */
  it('库龄合计恒等于四个年龄段之和', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (a, b, c, d) => {
          const result = calcAgingTotal(a, b, c, d)
          const expected = a + b + c + d
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 6 PBT: 单价=金额/数量 ───────────────────────────────────────

describe('Feature: f2-inventory-main, Property 6: 单价=金额/数量', () => {
  /**
   * **Validates: Requirements 18.5, 5.5**
   *
   * ∀ amount ∈ ℝ, qty ∈ ℝ\{0}:
   * calcUnitPrice(amount, qty) === amount/qty
   * calcUnitPrice(x, 0) === ''
   */
  it('单价恒等于金额除以数量（数量≠0）', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.001, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (amount, qty) => {
          const result = calcUnitPrice(amount, qty)
          const expected = amount / qty
          expect(result).toBeCloseTo(expected as number, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('数量为0时返回空串', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (amount) => {
          const result = calcUnitPrice(amount, 0)
          expect(result).toBe('')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 7 PBT: 变动率边界处理 ────────────────────────────────────────

describe('Feature: f2-inventory-main, Property 7: 变动率边界处理', () => {
  /**
   * **Validates: Requirements 18.8**
   *
   * calcChangeRate(0,0)===''; calcChangeRate(0,x)==='N/A'(x≠0);
   * calcChangeRate(a,b)===(b-a)/a (a≠0)
   */
  it('期初=0且期末=0时返回空串', () => {
    expect(calcChangeRate(0, 0)).toBe('')
  })

  it('期初=0且期末≠0时返回N/A', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }).filter(x => x !== 0),
        (current) => {
          const result = calcChangeRate(0, current)
          expect(result).toBe('N/A')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('期初≠0时变动率=(期末-期初)/期初', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }).filter(x => x !== 0),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (prior, current) => {
          const result = calcChangeRate(prior, current)
          const expected = (current - prior) / prior
          expect(result).toBeCloseTo(expected as number, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 8 PBT: 产销率公式 ────────────────────────────────────────────

describe('Feature: f2-inventory-main, Property 8: 产销率=销量/产量×100%', () => {
  /**
   * **Validates: Requirements 18.11, 9.5**
   *
   * ∀ sales, production ∈ ℝ>0:
   * calcProductionSalesRate(sales, production) === sales/production*100
   */
  it('产销率恒等于销量/产量×100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (sales, production) => {
          const result = calcProductionSalesRate(sales, production)
          const expected = (sales / production) * 100
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 9 PBT: 检查比例公式 ──────────────────────────────────────────

describe('Feature: f2-inventory-main, Property 9: 检查比例=检查金额/账面金额×100', () => {
  /**
   * **Validates: Requirements 18.10, 12.3**
   *
   * ∀ checked, total ∈ ℝ>0:
   * calcCoverageRatio(checked, total) === checked/total*100
   */
  it('检查比例恒等于检查金额/账面金额×100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (checked, total) => {
          const result = calcCoverageRatio(checked, total)
          const expected = (checked / total) * 100
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
