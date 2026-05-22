/**
 * numericSortMethod property tests + unit tests
 * **Validates: Requirements F3.2, F3.5**
 *
 * Property 3: Monotonicity — a < b → sort(a,b) < 0; null sorts to end
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { numericSortMethod } from '@/utils/numericSort'

const sorter = numericSortMethod('value')

describe('numericSortMethod — Property Tests', () => {
  it('P3: monotonicity — a < b → sort(a,b) < 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (a, b) => {
          fc.pre(a !== b)
          const rowA = { value: a }
          const rowB = { value: b }
          const result = sorter(rowA, rowB)
          if (a < b) return result < 0
          return result > 0
        },
      ),
      { numRuns: 30 },
    )
  })

  it('P3: null always sorts after valid numbers', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (a) => {
          const rowA = { value: a }
          const rowNull = { value: null }
          return sorter(rowA, rowNull) < 0 && sorter(rowNull, rowA) > 0
        },
      ),
      { numRuns: 30 },
    )
  })
})

describe('numericSortMethod — Unit Tests', () => {
  it('null sorts to end', () => {
    expect(sorter({ value: 5 }, { value: null })).toBeLessThan(0)
    expect(sorter({ value: null }, { value: 5 })).toBeGreaterThan(0)
  })

  it('NaN sorts to end', () => {
    expect(sorter({ value: 5 }, { value: NaN })).toBeLessThan(0)
    expect(sorter({ value: NaN }, { value: 5 })).toBeGreaterThan(0)
  })

  it('normal numeric sort', () => {
    expect(sorter({ value: 1 }, { value: 2 })).toBeLessThan(0)
    expect(sorter({ value: 10 }, { value: 3 })).toBeGreaterThan(0)
    expect(sorter({ value: 5 }, { value: 5 })).toBe(0)
  })

  it('two nulls are equal', () => {
    expect(sorter({ value: null }, { value: null })).toBe(0)
  })
})
