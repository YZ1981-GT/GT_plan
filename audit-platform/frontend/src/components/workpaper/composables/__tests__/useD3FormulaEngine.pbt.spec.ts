/**
 * Property-Based Tests — D3 预收账款公式引擎
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  isChangeRateExceeding,
} from '../useD3FormulaEngine'

const valArb = fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })

describe('Feature: d3-prepaid-accounts, Property 1: 审定数公式', () => {
  it('calcAuditedAmount = unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(valArb, valArb, valArb, (u, a, r) => {
        expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
      }),
      { numRuns: 50 },
    )
  })
})

describe('Feature: d3-prepaid-accounts, Property 2: 变动额/变动率', () => {
  it('calcChangeAmount = current - prior', () => {
    fc.assert(
      fc.property(valArb, valArb, (prior, current) => {
        expect(calcChangeAmount(current, prior)).toBeCloseTo(current - prior, 5)
      }),
      { numRuns: 50 },
    )
  })

  it('calcChangeRate handles zero prior', () => {
    expect(calcChangeRate(0, 0)).toBe('')
    expect(calcChangeRate(0, 100)).toBe('N/A')
    fc.assert(
      fc.property(fc.double({ min: 0.01, max: 1e8, noNaN: true }), valArb, (prior, current) => {
        const rate = calcChangeRate(prior, current)
        if (typeof rate === 'number') {
          expect(rate).toBeCloseTo((current - prior) / prior, 5)
        }
      }),
      { numRuns: 30 },
    )
  })
})

describe('Feature: d3-prepaid-accounts, Property 3: 合计行', () => {
  it('calcSubtotal equals sum', () => {
    fc.assert(
      fc.property(fc.array(valArb, { minLength: 0, maxLength: 20 }), (vals) => {
        expect(calcSubtotal(vals)).toBeCloseTo(vals.reduce((s, v) => s + v, 0), 5)
      }),
      { numRuns: 30 },
    )
  })
})

describe('Feature: d3-prepaid-accounts, Property 4: 变动率阈值', () => {
  it('isChangeRateExceeding respects threshold', () => {
    expect(isChangeRateExceeding(0.31, 0.3)).toBe(true)
    expect(isChangeRateExceeding(0.29, 0.3)).toBe(false)
    expect(isChangeRateExceeding('', 0.3)).toBe(false)
    expect(isChangeRateExceeding('N/A', 0.3)).toBe(false)
  })
})

describe('parseNum safety', () => {
  it('invalid values become 0', () => {
    fc.assert(
      fc.property(fc.constantFrom(null, undefined, '', 'abc', NaN), (v) => {
        expect(parseNum(v as any)).toBe(0)
      }),
    )
  })
})
