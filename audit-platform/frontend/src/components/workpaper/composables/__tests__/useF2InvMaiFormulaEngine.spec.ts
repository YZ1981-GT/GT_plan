import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcEndAmount,
  calcNetValue,
  calcAuditedEnd,
  calcSubtotal,
  calcAgingTotal,
  calcUnitPrice,
  calcChangeRate,
  calcProductionSalesRate,
  calcCoverageRatio,
  calcTurnoverRate,
} from '../useF2InvMaiFormulaEngine'

describe('useF2InvMaiFormulaEngine PBT', () => {
  it('Property 1: end balance = opening + increase - decrease', () => {
    fc.assert(fc.property(
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      (o, inc, dec) => {
        expect(calcEndAmount(o, inc, dec)).toBeCloseTo(o + inc - dec, 3)
        return true
      },
    ))
  })

  it('Property 2: net = gross - impairment', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      (g, i) => {
        expect(calcNetValue(g, i)).toBeCloseTo(g - i, 3)
        return true
      },
    ))
  })

  it('Property 3: audited end = opening + inc - dec + adj', () => {
    fc.assert(fc.property(
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      (o, inc, dec, adj) => {
        expect(calcAuditedEnd(o, inc, dec, adj)).toBeCloseTo(o + inc - dec + adj, 3)
        return true
      },
    ))
  })

  it('Property 4: subtotal = sum', () => {
    fc.assert(fc.property(
      fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 1, maxLength: 30 }),
      (arr) => {
        expect(calcSubtotal(arr)).toBeCloseTo(arr.reduce((a, b) => a + b, 0), 3)
        return true
      },
    ))
  })

  it('Property 5: aging total = sum of 4 segments', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      (a, b, c, d) => {
        expect(calcAgingTotal(a, b, c, d)).toBeCloseTo(a + b + c + d, 3)
        return true
      },
    ))
  })

  it('Property 6: unit price = amount/qty or empty', () => {
    fc.assert(fc.property(
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      fc.float({ min: Math.fround(0.001), max: 1e4, noNaN: true }),
      (amt, qty) => {
        expect(calcUnitPrice(amt, qty)).toBeCloseTo(amt / qty, 3)
        return true
      },
    ))
    expect(calcUnitPrice(100, 0)).toBe('')
  })

  it('Property 7: change rate boundaries', () => {
    expect(calcChangeRate(0, 0)).toBe('')
    expect(calcChangeRate(0, 5)).toBe('N/A')
    fc.assert(fc.property(
      fc.float({ min: Math.fround(0.001), max: 1e6, noNaN: true }),
      fc.float({ min: -1e6, max: 1e6, noNaN: true }),
      (prior, cur) => {
        const r = calcChangeRate(prior, cur)
        if (r !== '' && r !== 'N/A') expect(r).toBeCloseTo((cur - prior) / prior, 3)
        return true
      },
    ))
  })

  it('Property 8: production sales rate', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: Math.fround(0.1), max: 1e6, noNaN: true }),
      (sales, prod) => {
        expect(calcProductionSalesRate(sales, prod)).toBeCloseTo(sales / prod * 100, 3)
        return true
      },
    ))
  })

  it('Property 9: coverage ratio', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: Math.fround(0.01), max: 1e6, noNaN: true }),
      (checked, total) => {
        expect(calcCoverageRatio(checked, total)).toBeCloseTo(checked / total * 100, 3)
        return true
      },
    ))
  })

  it('parseNum handles invalid values', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum('12.5')).toBe(12.5)
  })

  it('turnover rate', () => {
    expect(calcTurnoverRate(1000, 500)).toBe(2)
    expect(calcTurnoverRate(1000, 0)).toBe(0)
  })
})
