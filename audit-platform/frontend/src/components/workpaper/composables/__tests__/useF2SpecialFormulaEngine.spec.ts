import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcRemainingCost,
  calcImpairment,
  isLossContract,
  calcExpectedLoss,
  calcSubtotalByCategory,
  calcEndBalance,
} from '../useF2SpecialFormulaEngine'

describe('useF2SpecialFormulaEngine', () => {
  it('calcRemainingCost = total - incurred', () => {
    expect(calcRemainingCost(1000, 400)).toBe(600)
  })

  it('Property: impairment >= 0', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      (book, recoverable) => {
        expect(calcImpairment(book, recoverable)).toBeGreaterThanOrEqual(0)
      },
    ))
  })

  it('Property: loss contract consistency', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      (rev, cost) => {
        expect(isLossContract(rev, cost)).toBe(cost > rev)
      },
    ))
  })

  it('calcSubtotalByCategory sums four categories', () => {
    expect(calcSubtotalByCategory(10, 20, 30, 40)).toBe(100)
  })

  it('calcEndBalance = opening + increase - decrease', () => {
    expect(calcEndBalance(100, 50, 30)).toBe(120)
  })

  it('calcExpectedLoss zero when not loss', () => {
    expect(calcExpectedLoss(1000, 800, 0.5)).toBe(0)
  })
})
