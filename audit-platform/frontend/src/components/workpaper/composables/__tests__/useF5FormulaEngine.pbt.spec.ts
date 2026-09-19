/**
 * Property-Based Tests — F5 营业成本公式引擎
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Tasks 2.2 ~ 2.11
 * 覆盖 Property 1~10
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAdjustedAmount,
  calcCostRollforward,
  calcGrossMargin,
  calcFinishedGoodsCost,
  calcCOGS,
  calcQuantityVariance,
  calcChangeRate,
  calcCoeffOfVariation,
  calcSubtotal,
  isDebitCreditBalanced,
} from '../useF5CosOfFormulaEngine'

const dbl = (min: number, max: number) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

// Property 1: 损益类审定公式
describe('Feature: f5-cost-of-sales, Property 1: 损益类审定公式', () => {
  it('calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(-1e8, 1e8), dbl(-1e8, 1e8), (unadjusted, aje, rje) => {
        expect(calcAdjustedAmount(unadjusted, aje, rje)).toBeCloseTo(unadjusted + aje + rje, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// Property 2: 成本倒轧恒等
describe('Feature: f5-cost-of-sales, Property 2: 成本倒轧恒等', () => {
  it('calcCostRollforward === opening + purchase - closing - other', () => {
    fc.assert(
      fc.property(dbl(0, 1e8), dbl(0, 1e8), dbl(0, 1e8), dbl(0, 1e8), (opening, purchase, closing, other) => {
        expect(calcCostRollforward(opening, purchase, closing, other)).toBeCloseTo(
          opening + purchase - closing - other,
          5,
        )
      }),
      { numRuns: 100 },
    )
  })
})

// Property 3: 毛利率公式
describe('Feature: f5-cost-of-sales, Property 3: 毛利率公式', () => {
  it('calcGrossMargin(revenue, cost) === (revenue-cost)/revenue × 100 when revenue > 0', () => {
    fc.assert(
      fc.property(dbl(0.01, 1e8), dbl(0, 1e8), (revenue, cost) => {
        const result = calcGrossMargin(revenue, cost)
        expect(result).not.toBe('N/A')
        expect(result as number).toBeCloseTo(((revenue - cost) / revenue) * 100, 4)
      }),
      { numRuns: 100 },
    )
  })

  it('returns N/A when revenue is 0', () => {
    expect(calcGrossMargin(0, 100)).toBe('N/A')
  })
})

// Property 4: 完工成本恒等
describe('Feature: f5-cost-of-sales, Property 4: 完工成本恒等', () => {
  it('calcFinishedGoodsCost === wipOpening + totalCost - wipClosing', () => {
    fc.assert(
      fc.property(dbl(0, 1e8), dbl(0, 1e8), dbl(0, 1e8), (wipOpening, totalCost, wipClosing) => {
        expect(calcFinishedGoodsCost(wipOpening, totalCost, wipClosing)).toBeCloseTo(
          wipOpening + totalCost - wipClosing,
          5,
        )
      }),
      { numRuns: 100 },
    )
  })
})

// Property 5: 营业成本倒轧全链非负（合理输入）
describe('Feature: f5-cost-of-sales, Property 5: 营业成本倒轧全链非负', () => {
  it('calcCOGS >= 0 when fgOpening + finishedCost >= fgClosing + other', () => {
    fc.assert(
      fc.property(dbl(0, 1e8), dbl(0, 1e8), dbl(0, 1e8), dbl(0, 1e8), (fgOpening, finishedCost, fgClosing, other) => {
        // 构造合理输入：期初+完工 ≥ 期末+其他
        const total = fgOpening + finishedCost
        const outflow = fgClosing + other
        const scaledClosing = outflow > total ? (fgClosing / (outflow || 1)) * total : fgClosing
        const scaledOther = outflow > total ? (other / (outflow || 1)) * total : other
        const cogs = calcCOGS(fgOpening, finishedCost, scaledClosing, scaledOther)
        expect(cogs).toBeGreaterThanOrEqual(-1e-6)
      }),
      { numRuns: 100 },
    )
  })
})

// Property 6: 数量差异公式
describe('Feature: f5-cost-of-sales, Property 6: 数量差异公式', () => {
  it('calcQuantityVariance(salesQty, costQty) === salesQty - costQty', () => {
    fc.assert(
      fc.property(dbl(0, 1e6), dbl(0, 1e6), (salesQty, costQty) => {
        expect(calcQuantityVariance(salesQty, costQty)).toBeCloseTo(salesQty - costQty, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// Property 7: 变动率公式
describe('Feature: f5-cost-of-sales, Property 7: 变动率公式', () => {
  it('calcChangeRate(current, prior) === (current-prior)/prior × 100 when prior != 0', () => {
    fc.assert(
      fc.property(dbl(-1e8, 1e8), dbl(0.01, 1e8), (current, prior) => {
        const result = calcChangeRate(current, prior)
        expect(result).not.toBe('N/A')
        expect(result as number).toBeCloseTo(((current - prior) / prior) * 100, 4)
      }),
      { numRuns: 100 },
    )
  })

  it('returns N/A when prior is 0', () => {
    expect(calcChangeRate(100, 0)).toBe('N/A')
  })
})

// Property 8: 波动系数非负
describe('Feature: f5-cost-of-sales, Property 8: 波动系数非负', () => {
  it('calcCoeffOfVariation(values) >= 0 for non-negative values with mean > 0', () => {
    fc.assert(
      fc.property(
        fc.array(dbl(0, 1e6), { minLength: 2, maxLength: 12 }),
        (values) => {
          const mean = values.reduce((s, v) => s + v, 0) / values.length
          fc.pre(mean > 0)
          expect(calcCoeffOfVariation(values)).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 when mean is 0 (all zeros)', () => {
    expect(calcCoeffOfVariation([0, 0, 0])).toBe(0)
  })
})

// Property 9: 月度合计恒等
describe('Feature: f5-cost-of-sales, Property 9: 月度合计恒等', () => {
  it('SUM(months[0..5]) + SUM(months[6..11]) === SUM(months[0..11])', () => {
    fc.assert(
      fc.property(
        fc.array(dbl(0, 1e6), { minLength: 12, maxLength: 12 }),
        (months) => {
          const h1 = calcSubtotal(months.slice(0, 6))
          const h2 = calcSubtotal(months.slice(6, 12))
          const year = calcSubtotal(months)
          expect(h1 + h2).toBeCloseTo(year, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// Property 10: 借贷平衡恒等
describe('Feature: f5-cost-of-sales, Property 10: 借贷平衡恒等', () => {
  it('isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(dbl(0, 1e6), { minLength: 1, maxLength: 20 }),
        fc.array(dbl(0, 1e6), { minLength: 1, maxLength: 20 }),
        (debits, credits) => {
          const d = debits.reduce((s, v) => s + v, 0)
          const c = credits.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(debits, credits)).toBe(Math.abs(d - c) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})
