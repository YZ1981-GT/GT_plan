/**
 * Property-Based Tests — F2 存货底稿截止判定幂等性
 *
 * Spec: .kiro/specs/f2-inventory-main/
 * Task: 12.2
 *
 * Property 12: 截止判定幂等
 *
 * **Validates: Requirements 18.13, 11.4**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import { isCutoffCorrect } from '../composables/useF2InvMaiFormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

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

// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: 截止判定幂等
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: f2-inventory-main, Property 12: 截止判定幂等', () => {
  /**
   * **Validates: Requirements 18.13, 11.4**
   *
   * ∀ docDate, bookDate, periodEnd ∈ 日期:
   * isCutoffCorrect(docDate, bookDate, periodEnd) 结果确定且幂等
   * 即：同输入多次调用始终返回相同结果
   */

  it('同输入多次调用返回相同结果（幂等性）', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        arbDateStr,
        (docDate, bookDate, periodEnd) => {
          const result1 = isCutoffCorrect(docDate, bookDate, periodEnd)
          const result2 = isCutoffCorrect(docDate, bookDate, periodEnd)
          const result3 = isCutoffCorrect(docDate, bookDate, periodEnd)
          expect(result1).toBe(result2)
          expect(result2).toBe(result3)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('结果始终为布尔值（确定性）', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        arbDateStr,
        (docDate, bookDate, periodEnd) => {
          const result = isCutoffCorrect(docDate, bookDate, periodEnd)
          expect(typeof result).toBe('boolean')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('入库日期和记账日期均≤期末 → 截止正确（同侧）', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        (docDate, bookDate) => {
          const later = docDate >= bookDate ? docDate : bookDate
          const result = isCutoffCorrect(docDate, bookDate, later)
          expect(result).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('单据与记账分落截止日两侧 → 跨期不正确', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        (bookDate, periodEnd) => {
          const endDate = new Date(periodEnd + 'T00:00:00')
          const docDateObj = new Date(endDate)
          docDateObj.setDate(docDateObj.getDate() + 1)
          const docDate = formatDate(docDateObj)

          const result = isCutoffCorrect(docDate, bookDate <= periodEnd ? bookDate : periodEnd, periodEnd)
          expect(result).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('记账在截止日后、单据在截止日前 → 跨期不正确', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        (docDate, periodEnd) => {
          const endDate = new Date(periodEnd + 'T00:00:00')
          const bookDateObj = new Date(endDate)
          bookDateObj.setDate(bookDateObj.getDate() + 1)
          const bookDate = formatDate(bookDateObj)

          const result = isCutoffCorrect(docDate <= periodEnd ? docDate : periodEnd, bookDate, periodEnd)
          expect(result).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('单据与记账均在截止日后 → 同侧正确', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        (periodEnd) => {
          const endDate = new Date(periodEnd + 'T00:00:00')
          const a = new Date(endDate); a.setDate(a.getDate() + 1)
          const b = new Date(endDate); b.setDate(b.getDate() + 3)
          expect(isCutoffCorrect(formatDate(a), formatDate(b), periodEnd)).toBe(true)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('参数顺序不影响幂等性（交换docDate和bookDate仍幂等）', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        arbDateStr,
        arbDateStr,
        (dateA, dateB, periodEnd) => {
          // 分别以两种参数顺序调用，各自结果稳定
          const r1a = isCutoffCorrect(dateA, dateB, periodEnd)
          const r1b = isCutoffCorrect(dateA, dateB, periodEnd)
          const r2a = isCutoffCorrect(dateB, dateA, periodEnd)
          const r2b = isCutoffCorrect(dateB, dateA, periodEnd)
          expect(r1a).toBe(r1b)
          expect(r2a).toBe(r2b)
        },
      ),
      { numRuns: 100 },
    )
  })
})
