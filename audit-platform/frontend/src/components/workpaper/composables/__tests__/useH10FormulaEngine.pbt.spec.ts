import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementNet,
  calcSubtotal,
  isDebitCreditBalanced,
} from '../useH10FormulaEngine'
import {
  calcDisposalGainLoss,
  calcNetBookValue,
  calcGainLossRate,
} from '../useH10DisposalCalcEngine'

describe('useH10FormulaEngine PBT', () => {
  it('Property P1: calcAuditedAmount = u + aje + rje', () => {
    fc.assert(fc.property(
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      fc.float({ noNaN: true }),
      (u, aje, rje) => {
        const uu = Number.isFinite(u) ? u : 0
        const aa = Number.isFinite(aje) ? aje : 0
        const rr = Number.isFinite(rje) ? rje : 0
        expect(calcAuditedAmount(uu, aa, rr)).toBeCloseTo(uu + aa + rr, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property P2: calcIncomeStatementNet = cr - dr', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      (cr, dr) => {
        expect(calcIncomeStatementNet(cr, dr)).toBeCloseTo(cr - dr, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property P3: calcDisposalGainLoss = income - netValue - expenses - tax', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      (income, netValue, expenses, tax) => {
        expect(calcDisposalGainLoss(income, netValue, expenses, tax))
          .toBeCloseTo(income - netValue - expenses - tax, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property P4: calcNetBookValue = cost - dep - impair', () => {
    fc.assert(fc.property(
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      fc.float({ min: 0, max: 1e9, noNaN: true }),
      (cost, dep, impair) => {
        expect(calcNetBookValue(cost, dep, impair)).toBeCloseTo(cost - dep - impair, 5)
        expect(calcNetBookValue(cost, dep)).toBeCloseTo(cost - dep, 5)
      },
    ), { numRuns: 50 })
  })

  it('Property P5: calcSubtotal = Σarr', () => {
    fc.assert(fc.property(fc.array(fc.float({ noNaN: true })), (arr) => {
      const expected = arr.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0)
      expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
    }), { numRuns: 50 })
  })

  it('Property P6: calcGainLossRate = gl/cost × 100', () => {
    fc.assert(fc.property(
      fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
      fc.float({ min: Math.fround(0.01), max: 1e9, noNaN: true, noDefaultInfinity: true }),
      (gl, cost) => {
        expect(calcGainLossRate(gl, cost)).toBeCloseTo((gl / cost) * 100, 5)
      },
    ), { numRuns: 50 })
  })

  it('calcGainLossRate returns null when cost is 0', () => {
    expect(calcGainLossRate(100, 0)).toBeNull()
  })

  it('parseNum robustness', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(42)).toBe(42)
  })

  it('isDebitCreditBalanced', () => {
    fc.assert(fc.property(fc.array(fc.float()), fc.array(fc.float()), (d, c) => {
      const ds = d.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0)
      const cs = c.reduce((s, v) => s + (Number.isFinite(v) ? v : 0), 0)
      expect(isDebitCreditBalanced(d, c)).toBe(Math.abs(ds - cs) < 0.01)
    }), { numRuns: 50 })
  })
})
