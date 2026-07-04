import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcNRV,
  calcImpairmentProvision,
  calcWeightedAvgPrice,
  calcPriceVariance,
  calcQuantityVariance,
  calcTotalVariance,
  calcReversalAmount,
} from '../useF2InvValFormulaEngine'

describe('useF2InvValFormulaEngine PBT', () => {
  it('Property 1: NRV formula', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      (price, completion, expense, tax) => {
        expect(calcNRV(price, completion, expense, tax)).toBeCloseTo(
          price - completion - expense - tax,
          3,
        )
      },
    ))
  })

  it('Property 2: impairment provision', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      (book, nrv) => {
        expect(calcImpairmentProvision(book, nrv)).toBeCloseTo(Math.max(0, book - nrv), 3)
      },
    ))
  })

  it('Property 3: weighted average price', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: Math.fround(0.01), max: 1e4, noNaN: true }),
      fc.float({ min: Math.fround(0.01), max: 1e4, noNaN: true }),
      (oAmt, iAmt, oQty, iQty) => {
        expect(calcWeightedAvgPrice(oAmt, iAmt, oQty, iQty)).toBeCloseTo(
          (oAmt + iAmt) / (oQty + iQty),
          3,
        )
      },
    ))
  })

  it('Property 4: variance identity', () => {
    fc.assert(fc.property(
      fc.float({ min: -1e3, max: 1e3, noNaN: true }),
      fc.float({ min: -1e3, max: 1e3, noNaN: true }),
      fc.float({ min: -1e3, max: 1e3, noNaN: true }),
      fc.float({ min: -1e3, max: 1e3, noNaN: true }),
      (actP, stdP, actQ, stdQ) => {
        const total = calcTotalVariance(actP, actQ, stdP, stdQ)
        const sum = calcPriceVariance(actP, stdP, actQ) + calcQuantityVariance(actQ, stdQ, stdP)
        expect(total).toBeCloseTo(sum, 3)
      },
    ))
  })

  it('Property 5: reversal bounded', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      fc.float({ min: 0, max: 1e6, noNaN: true }),
      (existing, required, cap) => {
        const r = calcReversalAmount(existing, required, cap)
        expect(r).toBeGreaterThanOrEqual(0)
        expect(r).toBeLessThanOrEqual(cap + 0.001)
      },
    ))
  })
})
