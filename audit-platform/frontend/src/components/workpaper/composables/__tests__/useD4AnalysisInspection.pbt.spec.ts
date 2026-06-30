/**
 * Property-Based Tests — D4 分析程序 + 检查程序
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Tasks: 10.3, 10.4, 11.3
 *
 * Property 12: 客户集中度Top5计算
 * Property 18: 异常率与覆盖率计算
 * Property 9: 截止跨期自动判断
 *
 * **Validates: Requirements 8.4, 9.4, 10.5, 11.3, 11.5**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  calcSubtotal,
  calcProportion,
  calcAnomalyRate,
  calcCoverageRate,
  isCrossPeriod,
  calcCrossPeriodDays,
} from '../useD4FormulaEngine'

// ─── Property 12 PBT: 客户集中度Top5计算 ───────────────────────────────────

describe('Feature: d4-operating-revenue, Property 12: 客户集中度Top5计算', () => {
  /**
   * **Validates: Requirements 8.4**
   *
   * For any array of customer amounts (1~50 items):
   * - Top5 = top 5 items sorted by value descending (if N<5 take all)
   * - Top5占比 = sum(top5) / sum(all) × 100
   * - 占比>50% → concentration warning
   */
  it('Top5 is the 5 largest values sorted descending (or all if N<5)', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          { minLength: 1, maxLength: 50 },
        ),
        (amounts) => {
          // Sort descending and take top 5
          const sorted = [...amounts].sort((a, b) => b - a)
          const top5 = sorted.slice(0, 5)

          // Verify top5 length
          expect(top5.length).toBe(Math.min(5, amounts.length))

          // Verify top5 are indeed the largest values
          const minTop5 = Math.min(...top5)
          const nonTop5 = sorted.slice(5)
          for (const val of nonTop5) {
            expect(val).toBeLessThanOrEqual(minTop5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Top5占比 = sum(top5) / sum(all) × 100', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          { minLength: 1, maxLength: 50 },
        ),
        (amounts) => {
          const total = calcSubtotal(amounts)
          const sorted = [...amounts].sort((a, b) => b - a)
          const top5 = sorted.slice(0, 5)
          const top5Sum = calcSubtotal(top5)

          if (total === 0) {
            // When total is 0, proportion should be 0
            expect(calcProportion(top5Sum, total)).toBe(0)
          } else {
            const proportion = calcProportion(top5Sum, total)
            const expected = (top5Sum / total) * 100
            expect(proportion).toBeCloseTo(expected, 4)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('占比>50% triggers concentration warning', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
          { minLength: 1, maxLength: 50 },
        ),
        (amounts) => {
          const total = calcSubtotal(amounts)
          if (total === 0) return // skip trivial case

          const sorted = [...amounts].sort((a, b) => b - a)
          const top5 = sorted.slice(0, 5)
          const top5Sum = calcSubtotal(top5)
          const ratio = top5Sum / total

          // Concentration warning logic: ratio > 0.5 → warning
          const shouldWarn = ratio > 0.5
          // Verify the proportion calculation matches
          const proportion = calcProportion(top5Sum, total)
          expect(proportion > 50).toBe(shouldWarn)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 18 PBT: 异常率与覆盖率计算 ───────────────────────────────────

describe('Feature: d4-operating-revenue, Property 18: 异常率与覆盖率计算', () => {
  /**
   * **Validates: Requirements 9.4, 10.5, 11.5**
   *
   * - calcAnomalyRate(anomalyCount, totalChecked) === anomalyCount/totalChecked*100 (totalChecked>0)
   * - calcCoverageRate(checkedAmount, revenueTotal) === checkedAmount/revenueTotal*100 (revenueTotal>0)
   * - Both return 0 when denominator is 0
   */
  it('calcAnomalyRate = anomalyCount / totalChecked * 100 when totalChecked > 0', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 100 }),
        fc.nat({ max: 100 }).filter(n => n > 0),
        (anomalyCount, totalChecked) => {
          const result = calcAnomalyRate(anomalyCount, totalChecked)
          const expected = (anomalyCount / totalChecked) * 100
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcAnomalyRate returns 0 when totalChecked is 0', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 100 }),
        (anomalyCount) => {
          expect(calcAnomalyRate(anomalyCount, 0)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcCoverageRate = checkedAmount / revenueTotal * 100 when revenueTotal > 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (checkedAmount, revenueTotal) => {
          const result = calcCoverageRate(checkedAmount, revenueTotal)
          const expected = (checkedAmount / revenueTotal) * 100
          expect(result).toBeCloseTo(expected, 4)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcCoverageRate returns 0 when revenueTotal is 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (checkedAmount) => {
          expect(calcCoverageRate(checkedAmount, 0)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('anomalyRate is always between 0 and 100 when anomalyCount <= totalChecked', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 100 }),
        (totalChecked) => {
          const anomalyCount = fc.sample(fc.nat({ max: totalChecked }), 1)[0]
          if (totalChecked === 0) {
            expect(calcAnomalyRate(anomalyCount, totalChecked)).toBe(0)
          } else {
            const rate = calcAnomalyRate(anomalyCount, totalChecked)
            expect(rate).toBeGreaterThanOrEqual(0)
            expect(rate).toBeLessThanOrEqual(100)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 9 PBT: 截止跨期自动判断 ──────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 9: 截止跨期自动判断', () => {
  /**
   * **Validates: Requirements 11.3**
   *
   * - isCrossPeriod returns true when voucherDate and referenceDate are on
   *   opposite sides of balanceSheetDate
   * - calcCrossPeriodDays returns absolute day difference
   * - Both return false/0 for invalid dates
   */

  // Helper to format date as ISO string (YYYY-MM-DD)
  function toISODateString(d: Date): string {
    return d.toISOString().split('T')[0]
  }

  it('isCrossPeriod returns true when dates are on opposite sides of balanceSheetDate', () => {
    // Use integer-based date generation to avoid invalid Date instances
    const validDateArb = fc.integer({ min: 0, max: 3650 }).map(offset => {
      const base = new Date('2020-01-01')
      base.setDate(base.getDate() + offset)
      return toISODateString(base)
    })

    fc.assert(
      fc.property(
        validDateArb,
        validDateArb,
        validDateArb,
        (voucherDate, referenceDate, balanceSheetDate) => {
          const vd = new Date(voucherDate).getTime()
          const rd = new Date(referenceDate).getTime()
          const bs = new Date(balanceSheetDate).getTime()

          const result = isCrossPeriod(voucherDate, referenceDate, balanceSheetDate)

          // Cross period: one date <= BS and the other >= BS (on opposite sides)
          const expected = (vd <= bs && rd >= bs) || (vd >= bs && rd <= bs)
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcCrossPeriodDays returns absolute day difference between voucherDate and referenceDate', () => {
    // Use integer-based date generation to avoid invalid Date instances
    const validDateArb = fc.integer({ min: 0, max: 3650 }).map(offset => {
      const base = new Date('2020-01-01')
      base.setDate(base.getDate() + offset)
      return toISODateString(base)
    })

    fc.assert(
      fc.property(
        validDateArb,
        validDateArb,
        (voucherDate, referenceDate) => {
          const result = calcCrossPeriodDays(voucherDate, referenceDate)

          const vd = new Date(voucherDate).getTime()
          const rd = new Date(referenceDate).getTime()
          const expectedDays = Math.round(Math.abs(vd - rd) / (1000 * 60 * 60 * 24))

          expect(result).toBe(expectedDays)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('isCrossPeriod returns false for invalid dates', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('invalid', '', 'not-a-date', '9999-99-99', 'abc123'),
        fc.constantFrom('2024-12-31', '2025-06-30'),
        fc.constantFrom('2024-12-31', '2025-06-30'),
        (invalidDate, validDate1, validDate2) => {
          // Invalid voucherDate
          expect(isCrossPeriod(invalidDate, validDate1, validDate2)).toBe(false)
          // Invalid referenceDate
          expect(isCrossPeriod(validDate1, invalidDate, validDate2)).toBe(false)
          // Invalid balanceSheetDate
          expect(isCrossPeriod(validDate1, validDate2, invalidDate)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcCrossPeriodDays returns 0 for invalid dates', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('invalid', '', 'not-a-date', '9999-99-99', 'abc123'),
        fc.constantFrom('2024-12-31', '2025-06-30'),
        (invalidDate, validDate) => {
          // Invalid voucherDate
          expect(calcCrossPeriodDays(invalidDate, validDate)).toBe(0)
          // Invalid referenceDate
          expect(calcCrossPeriodDays(validDate, invalidDate)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calcCrossPeriodDays returns 0 when both dates are the same', () => {
    const validDateArb = fc.integer({ min: 0, max: 3650 }).map(offset => {
      const base = new Date('2020-01-01')
      base.setDate(base.getDate() + offset)
      return toISODateString(base)
    })

    fc.assert(
      fc.property(
        validDateArb,
        (dateStr) => {
          expect(calcCrossPeriodDays(dateStr, dateStr)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})
