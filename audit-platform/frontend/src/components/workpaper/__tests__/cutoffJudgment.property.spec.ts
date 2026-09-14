/**
 * Property-Based Tests — 截止测试跨期判定纯函数
 *
 * Spec: .kiro/specs/cutoff-test-auto-sampling/
 * Tasks: 5.2, 5.3
 *
 * 使用 fast-check + vitest 验证 Property 1 & Property 2。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { determineCutoffStatus, computeDateRange } from '../composables/cutoffJudgment'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Format a Date object to YYYY-MM-DD string */
function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Generate a valid date string in YYYY-MM-DD format */
const arbDateStr = fc
  .date({ min: new Date('2000-01-01T00:00:00'), max: new Date('2099-12-31T00:00:00') })
  .map(formatDate)
  .filter(s => !s.includes('NaN'))

/** Generate a cutoff direction */
const arbDirection = fc.constantFrom('post_cutoff' as const, 'pre_cutoff' as const, 'window' as const)

/** Generate a financial amount (positive or negative) */
const arbAmount = fc.float({ min: Math.fround(-1e9), max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true })

/** Generate days before/after (0-60) */
const arbDays = fc.integer({ min: 0, max: 60 })

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: 跨期判定纯函数正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: cutoff-test-auto-sampling, Property 1: 跨期判定纯函数正确性', () => {
  /**
   * **Validates: Requirements 6.1, 6.2, 6.3**
   *
   * 对任意 voucherDate, cutoffDate, direction, amount:
   * - 结果始终为三值枚举之一
   * - post_cutoff: voucherDate > cutoffDate AND amount > 0 → "可能跨期"
   * - pre_cutoff: voucherDate < cutoffDate AND amount < 0 → "可能跨期"
   * - window: voucherDate in [cutoff - daysBefore, cutoff + daysAfter] → "待检查"
   */

  it('result is always one of exactly three values', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        arbDirection,
        arbAmount,
        arbDays,
        arbDays,
        (voucherDate, cutoffDate, direction, amount, daysBefore, daysAfter) => {
          const result = determineCutoffStatus(
            voucherDate, cutoffDate, direction, amount, daysBefore, daysAfter,
          )
          expect(['可能跨期', '待检查', '正常']).toContain(result)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('post_cutoff: voucherDate > cutoffDate AND amount > 0 → "可能跨期"', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        fc.float({ min: Math.fround(0.01), max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
        arbDays,
        arbDays,
        (voucherDate, cutoffDate, amount, daysBefore, daysAfter) => {
          // Only test when voucherDate > cutoffDate
          if (voucherDate <= cutoffDate) return // skip non-applicable cases

          const result = determineCutoffStatus(
            voucherDate, cutoffDate, 'post_cutoff', amount, daysBefore, daysAfter,
          )
          expect(result).toBe('可能跨期')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('pre_cutoff: voucherDate < cutoffDate AND amount < 0 → "可能跨期"', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        fc.float({ min: Math.fround(-1e9), max: Math.fround(-0.01), noNaN: true, noDefaultInfinity: true }),
        arbDays,
        arbDays,
        (voucherDate, cutoffDate, amount, daysBefore, daysAfter) => {
          // Only test when voucherDate < cutoffDate
          if (voucherDate >= cutoffDate) return // skip non-applicable cases

          const result = determineCutoffStatus(
            voucherDate, cutoffDate, 'pre_cutoff', amount, daysBefore, daysAfter,
          )
          expect(result).toBe('可能跨期')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('window: voucherDate in [cutoff - daysBefore, cutoff + daysAfter] → "待检查"', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDays,
        arbDays,
        arbAmount,
        (cutoffDate, daysBefore, daysAfter, amount) => {
          // Compute a voucherDate guaranteed to be inside the window
          const { start, end } = computeDateRange(cutoffDate, daysBefore, daysAfter)

          // Use cutoffDate itself (always in window since daysBefore >= 0 and daysAfter >= 0)
          const result = determineCutoffStatus(
            cutoffDate, cutoffDate, 'window', amount, daysBefore, daysAfter,
          )
          expect(result).toBe('待检查')

          // Also test with start boundary
          const resultStart = determineCutoffStatus(
            start, cutoffDate, 'window', amount, daysBefore, daysAfter,
          )
          expect(resultStart).toBe('待检查')

          // Also test with end boundary
          const resultEnd = determineCutoffStatus(
            end, cutoffDate, 'window', amount, daysBefore, daysAfter,
          )
          expect(resultEnd).toBe('待检查')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('post_cutoff: voucherDate <= cutoffDate OR amount <= 0 → "正常"', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        arbAmount,
        arbDays,
        arbDays,
        (voucherDate, cutoffDate, amount, daysBefore, daysAfter) => {
          // Test cases where condition is NOT met
          if (voucherDate > cutoffDate && amount > 0) return // skip the "可能跨期" case

          const result = determineCutoffStatus(
            voucherDate, cutoffDate, 'post_cutoff', amount, daysBefore, daysAfter,
          )
          expect(result).toBe('正常')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('pre_cutoff: voucherDate >= cutoffDate OR amount >= 0 → "正常"', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        arbAmount,
        arbDays,
        arbDays,
        (voucherDate, cutoffDate, amount, daysBefore, daysAfter) => {
          // Test cases where condition is NOT met
          if (voucherDate < cutoffDate && amount < 0) return // skip the "可能跨期" case

          const result = determineCutoffStatus(
            voucherDate, cutoffDate, 'pre_cutoff', amount, daysBefore, daysAfter,
          )
          expect(result).toBe('正常')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 日期窗口计算正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: cutoff-test-auto-sampling, Property 2: 日期窗口计算正确性', () => {
  /**
   * **Validates: Requirements 1.3, 2.5**
   *
   * 对任意 cutoffDate (YYYY-MM-DD), daysBefore (0-60), daysAfter (0-60):
   * - range_start = cutoffDate - daysBefore 天
   * - range_end = cutoffDate + daysAfter 天
   * - start <= cutoff <= end
   */

  it('range_start = cutoffDate - daysBefore days, range_end = cutoffDate + daysAfter days', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDays,
        arbDays,
        (cutoffDate, daysBefore, daysAfter) => {
          const { start, end } = computeDateRange(cutoffDate, daysBefore, daysAfter)

          // Compute expected start and end manually
          const baseDate = new Date(cutoffDate + 'T00:00:00')
          const expectedStart = new Date(baseDate)
          expectedStart.setDate(expectedStart.getDate() - daysBefore)
          const expectedEnd = new Date(baseDate)
          expectedEnd.setDate(expectedEnd.getDate() + daysAfter)

          expect(start).toBe(formatDate(expectedStart))
          expect(end).toBe(formatDate(expectedEnd))
        },
      ),
      { numRuns: 100 },
    )
  })

  it('start <= cutoffDate <= end', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDays,
        arbDays,
        (cutoffDate, daysBefore, daysAfter) => {
          const { start, end } = computeDateRange(cutoffDate, daysBefore, daysAfter)

          // String comparison works for YYYY-MM-DD format
          expect(start <= cutoffDate).toBe(true)
          expect(cutoffDate <= end).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('total window span = daysBefore + daysAfter days', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDays,
        arbDays,
        (cutoffDate, daysBefore, daysAfter) => {
          const { start, end } = computeDateRange(cutoffDate, daysBefore, daysAfter)

          const startDate = new Date(start + 'T00:00:00')
          const endDate = new Date(end + 'T00:00:00')
          const spanDays = Math.round((endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000))

          expect(spanDays).toBe(daysBefore + daysAfter)
        },
      ),
      { numRuns: 100 },
    )
  })
})
