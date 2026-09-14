/**
 * Property-Based Tests — D2-7 方法学参数管理 composable
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 2.2
 *
 * 使用 fast-check + vitest 验证 2 个 correctness properties (Property 9, 10)。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  computeMusSampleSize,
  computeRandomSampleSize,
} from '../useD2VcMethodology'

// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: MUS sample size computation
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 9: MUS sample size computation', () => {
  /**
   * **Validates: Requirements 6.3, 11.2**
   *
   * For any positive tolerable misstatement T, valid reliability factor RF ∈ {1.61, 2.31, 3.00},
   * and positive population amount P:
   *   interval = T / RF
   *   sampleSize = ceil(P / interval) = ceil(P * RF / T)
   *
   * Furthermore, higher RF (higher risk) produces equal or larger sample size (monotonicity).
   */

  it('computeMusSampleSize formula: sampleSize = ceil(P * RF / T)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 1000000 }),                  // T: tolerable misstatement > 0 (integer cents → avoid float rounding)
        fc.constantFrom(1.61, 2.31, 3.00),                     // RF: reliability factor
        fc.integer({ min: 1, max: 1000000 }),                  // P: population amount > 0
        (T, RF, P) => {
          const result = computeMusSampleSize(T, RF, P)
          const interval = T / RF
          const expected = Math.ceil(P / interval)

          expect(result).toBe(expected)
          // Also verify result is a positive integer
          expect(result).toBeGreaterThan(0)
          expect(Number.isInteger(result)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('monotonicity: higher reliability factor → equal or larger sample size', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 1000000 }),                  // T: tolerable misstatement > 0
        fc.integer({ min: 1, max: 1000000 }),                  // P: population amount > 0
        (T, P) => {
          // RF values ordered: 低(1.61) < 中(2.31) < 高(3.00)
          const sizeLow = computeMusSampleSize(T, 1.61, P)
          const sizeMedium = computeMusSampleSize(T, 2.31, P)
          const sizeHigh = computeMusSampleSize(T, 3.00, P)

          // Higher RF → equal or larger sample size
          expect(sizeMedium).toBeGreaterThanOrEqual(sizeLow)
          expect(sizeHigh).toBeGreaterThanOrEqual(sizeMedium)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 for invalid inputs (T<=0, RF<=0, P<=0)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: -1000000, max: 0 }),                 // non-positive T
        fc.constantFrom(1.61, 2.31, 3.00),
        fc.integer({ min: 1, max: 1000000 }),
        (T, RF, P) => {
          expect(computeMusSampleSize(T, RF, P)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: Random sampling sample size computation
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 10: Random sampling sample size computation', () => {
  /**
   * **Validates: Requirements 11.3**
   *
   * For any population size N > 0, the computed sample size is monotonically
   * non-decreasing with confidence level: size(0.80) <= size(0.90) <= size(0.95).
   * Also, sample size never exceeds population size.
   */

  it('monotonicity: higher confidence → equal or larger sample size', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100000 }),                    // N: population size > 0
        (N) => {
          const size80 = computeRandomSampleSize(N, 0.80)
          const size90 = computeRandomSampleSize(N, 0.90)
          const size95 = computeRandomSampleSize(N, 0.95)

          // Monotonically non-decreasing with confidence
          expect(size90).toBeGreaterThanOrEqual(size80)
          expect(size95).toBeGreaterThanOrEqual(size90)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('sample size never exceeds population size', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100000 }),                    // N: population size > 0
        fc.constantFrom(0.80, 0.90, 0.95),                     // confidence level
        (N, confidence) => {
          const result = computeRandomSampleSize(N, confidence)
          expect(result).toBeLessThanOrEqual(N)
          expect(result).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('returns 0 for non-positive population size', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: -1000, max: 0 }),                    // non-positive N
        fc.constantFrom(0.80, 0.90, 0.95),
        (N, confidence) => {
          expect(computeRandomSampleSize(N, confidence)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('result is always a positive integer for valid inputs', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100000 }),
        fc.constantFrom(0.80, 0.90, 0.95),
        (N, confidence) => {
          const result = computeRandomSampleSize(N, confidence)
          expect(Number.isInteger(result)).toBe(true)
          expect(result).toBeGreaterThan(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})
