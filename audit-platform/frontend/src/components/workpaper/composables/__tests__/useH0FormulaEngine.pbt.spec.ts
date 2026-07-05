import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcBlockTotal,
  calcCheckRatio,
  calcRowVariance,
  isAbnormal,
  parseNum,
} from '../../confirmation/alternativeH05/composables/useH0FormulaEngine'

describe('useH0FormulaEngine PBT', () => {
  it('calcBlockTotal sums finite numbers', () => {
    fc.assert(
      fc.property(fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { maxLength: 20 }), (arr) => {
        const expected = arr.reduce((s, v) => s + v, 0)
        expect(calcBlockTotal(arr)).toBeCloseTo(expected, 5)
      }),
    )
  })

  it('calcCheckRatio returns 0 when balance <= 0', () => {
    fc.assert(
      fc.property(fc.float({ min: -1e6, max: 1e6, noNaN: true }), (checked) => {
        expect(calcCheckRatio(checked, 0)).toBe(0)
        expect(calcCheckRatio(checked, -100)).toBe(0)
      }),
    )
  })

  it('calcCheckRatio = checked / balance when balance > 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e6, noNaN: true }),
        fc.float({ min: Math.fround(0.01), max: 1e6, noNaN: true }),
        (checked, balance) => {
          expect(calcCheckRatio(checked, balance)).toBeCloseTo(checked / balance, 10)
        },
      ),
    )
  })

  it('calcRowVariance = book - evidence', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (book, evidence) => {
          expect(calcRowVariance(book, evidence)).toBeCloseTo(book - evidence, 5)
        },
      ),
    )
  })

  it('isAbnormal true iff variance != 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (v) => {
          expect(isAbnormal(v)).toBe(v !== 0)
        },
      ),
    )
  })

  it('parseNum maps non-finite to 0', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(null)).toBe(0)
    expect(parseNum(42)).toBe(42)
  })
})
