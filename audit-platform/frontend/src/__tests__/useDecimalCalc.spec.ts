/**
 * useDecimalCalc property tests + unit tests
 * **Validates: Requirements F1.4**
 *
 * Property 1: Decimal add/sub round-trip — add(a, b) then sub(result, b) ≈ a (within 1e-10)
 * Property 2: Decimal mul/div round-trip — mul(a, b) then div(result, b) ≈ a (b≠0, within 1e-10)
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { useDecimalCalc } from '@/composables/useDecimalCalc'

const { add, sub, mul, div } = useDecimalCalc({ dp: 10 })
const calc2 = useDecimalCalc({ dp: 2 })

describe('useDecimalCalc — Property Tests', () => {
  it('P1: add/sub round-trip preserves value within 1e-10', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        (a, b) => {
          const sum = add(a, b)
          const result = sub(sum, b)
          const diff = Math.abs(parseFloat(result) - a)
          return diff < 1e-10
        },
      ),
      { numRuns: 30 },
    )
  })

  it('P2: mul/div round-trip preserves value within 1e-10 (b≠0)', () => {
    // Use higher dp to avoid intermediate rounding loss
    const hpCalc = useDecimalCalc({ dp: 15 })
    fc.assert(
      fc.property(
        fc.double({ min: -1e4, max: 1e4, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e3, noNaN: true, noDefaultInfinity: true }),
        (a, b) => {
          const product = hpCalc.mul(a, b)
          const result = hpCalc.div(product, b)
          const diff = Math.abs(parseFloat(result) - a)
          return diff < 1e-10
        },
      ),
      { numRuns: 30 },
    )
  })
})

describe('useDecimalCalc — Unit Tests', () => {
  it('0.1 + 0.2 = 0.30 (classic floating point trap)', () => {
    expect(calc2.add(0.1, 0.2)).toBe('0.30')
  })

  it('divide by zero returns 0.00', () => {
    expect(calc2.div(100, 0)).toBe('0.00')
  })

  it('non-numeric input returns 0.00', () => {
    expect(calc2.add('abc' as any, 1)).toBe('0.00')
  })
})
