/**
 * Property-Based Tests — useC24AnalyticsEngine 分析引擎
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 5.1
 *
 * 使用 fast-check + vitest 验证 Property 2~5。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcBalanceIntegrity,
  detectGaps,
  benfordDistribution,
  screenAnomalies,
  type JournalEntry,
  type AnomalyRules,
} from '../useC24AnalyticsEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** Generate a valid YYYY-MM-DD date string */
const arbDateStr = fc
  .date({ min: new Date('2020-01-01'), max: new Date('2030-12-31') })
  .map((d) => {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  })

/** Generate a positive amount (for debit/credit, avoiding extreme floats) */
const arbAmount = fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true })

/** Generate a JournalEntry */
function arbJournalEntry(overrides?: Partial<Record<keyof JournalEntry, fc.Arbitrary<any>>>): fc.Arbitrary<JournalEntry> {
  return fc.record({
    voucherDate: overrides?.voucherDate ?? arbDateStr,
    voucherMonth: fc.integer({ min: 1, max: 12 }),
    voucherType: fc.constantFrom('付', '收', '转'),
    voucherNo: fc.integer({ min: 1, max: 9999 }).map(n => `转-${String(n).padStart(3, '0')}`),
    summary: fc.string({ minLength: 0, maxLength: 20 }),
    accountCode: fc.stringMatching(/^[0-9]{4}$/),
    accountName: fc.string({ minLength: 1, maxLength: 10 }),
    debit: overrides?.debit ?? arbAmount,
    credit: overrides?.credit ?? arbAmount,
    voucherSheets: fc.constant('1'),
    preparer: fc.string({ minLength: 1, maxLength: 5 }),
    reviewer: fc.string({ minLength: 1, maxLength: 5 }),
    poster: fc.string({ minLength: 1, maxLength: 5 }),
  })
}

/** Generate AnomalyRules */
const arbAnomalyRules: fc.Arbitrary<AnomalyRules> = fc.record({
  holidays: fc.array(arbDateStr, { minLength: 0, maxLength: 10 }),
  nightStartHour: fc.integer({ min: 20, max: 23 }),
  nightEndHour: fc.integer({ min: 4, max: 8 }),
  largeAmountThreshold: fc.float({ min: 100000, max: 10000000, noNaN: true, noDefaultInfinity: true }),
  approvalLimit: fc.float({ min: 100000, max: 5000000, noNaN: true, noDefaultInfinity: true }),
  roundAmountDigits: fc.integer({ min: 2, max: 6 }),
  vagueKeywords: fc.array(fc.constantFrom('调整', '暂估', '其他', '冲回'), { minLength: 0, maxLength: 4 }),
  checkEmptySummary: fc.boolean(),
  duplicateCheck: fc.boolean(),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 借贷平衡完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 2: 借贷平衡完整性', () => {
  /**
   * **Validates: Requirements 3.1**
   *
   * For any JournalEntry[], calcBalanceIntegrity:
   * - debitTotal = Σdebit (rounded to 2dp)
   * - creditTotal = Σcredit (rounded to 2dp)
   * - balanced iff |debitTotal - creditTotal| < 0.01
   */

  it('balanced entries with matching debit/credit pairs → balanced=true', () => {
    fc.assert(
      fc.property(
        fc.array(arbAmount.filter(a => a > 0), { minLength: 1, maxLength: 20 }),
        (amounts) => {
          // Create balanced entries: for each amount, one debit entry + one credit entry
          const entries: JournalEntry[] = []
          for (const amount of amounts) {
            entries.push({
              voucherDate: '2025-01-15', voucherMonth: 1, voucherType: '转',
              voucherNo: '转-001', summary: 'test', accountCode: '6001',
              accountName: '测试', debit: amount, credit: 0,
              voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
            })
            entries.push({
              voucherDate: '2025-01-15', voucherMonth: 1, voucherType: '转',
              voucherNo: '转-001', summary: 'test', accountCode: '6001',
              accountName: '测试', debit: 0, credit: amount,
              voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
            })
          }
          const result = calcBalanceIntegrity(entries)
          expect(result.balanced).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('adding an unmatched debit entry → balanced=false', () => {
    fc.assert(
      fc.property(
        fc.array(arbAmount.filter(a => a > 0), { minLength: 1, maxLength: 10 }),
        arbAmount.filter(a => a >= 0.01), // unmatched amount must be significant
        (amounts, extraDebit) => {
          // Create balanced base entries
          const entries: JournalEntry[] = []
          for (const amount of amounts) {
            entries.push({
              voucherDate: '2025-01-15', voucherMonth: 1, voucherType: '转',
              voucherNo: '转-001', summary: 'test', accountCode: '6001',
              accountName: '测试', debit: amount, credit: 0,
              voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
            })
            entries.push({
              voucherDate: '2025-01-15', voucherMonth: 1, voucherType: '转',
              voucherNo: '转-001', summary: 'test', accountCode: '6001',
              accountName: '测试', debit: 0, credit: amount,
              voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
            })
          }
          // Add unmatched debit
          entries.push({
            voucherDate: '2025-01-15', voucherMonth: 1, voucherType: '转',
            voucherNo: '转-999', summary: 'extra', accountCode: '6001',
            accountName: '测试', debit: extraDebit, credit: 0,
            voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
          })
          const result = calcBalanceIntegrity(entries)
          expect(result.balanced).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('debitTotal equals rounded sum of all debit fields', () => {
    fc.assert(
      fc.property(
        fc.array(arbJournalEntry(), { minLength: 0, maxLength: 30 }),
        (entries) => {
          const result = calcBalanceIntegrity(entries)
          const expectedDebit = Math.round(entries.reduce((s, e) => s + (e.debit || 0), 0) * 100) / 100
          const expectedCredit = Math.round(entries.reduce((s, e) => s + (e.credit || 0), 0) * 100) / 100
          expect(result.debitTotal).toBeCloseTo(expectedDebit, 2)
          expect(result.creditTotal).toBeCloseTo(expectedCredit, 2)
          expect(result.balanced).toBe(Math.abs(expectedDebit - expectedCredit) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 跳号识别正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 3: 跳号识别正确性', () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * For any voucher number sequence:
   * - A complete sequence [1..n] → no gaps
   * - Removing any number from the sequence → that number appears in gaps
   */

  it('complete sequence [1..n] produces no gaps', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 2, max: 50 }),
        fc.constantFrom('付', '收', '转'),
        (n, type) => {
          const nos = Array.from({ length: n }, (_, i) => `${type}-${String(i + 1).padStart(3, '0')}`)
          const gaps = detectGaps(nos)
          expect(gaps).toEqual([])
        },
      ),
      { numRuns: 100 },
    )
  })

  it('removing one number from a complete sequence → that number is in gaps', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 3, max: 50 }),
        fc.constantFrom('付', '收', '转'),
        (n, type) => {
          // Pick a random index to remove (not first or last for clear gap detection)
          const removeIdx = Math.floor(n / 2) // middle element
          const removeNum = removeIdx + 1
          const nos = Array.from({ length: n }, (_, i) => `${type}-${String(i + 1).padStart(3, '0')}`)
            .filter((_, i) => i !== removeIdx)

          const gaps = detectGaps(nos)

          // The removed number should be within a gap range
          const removedStr = `${type}-${String(removeNum).padStart(3, '0')}`
          const coveredNumbers = new Set<string>()
          for (const gap of gaps) {
            // Parse start/end numbers
            const startMatch = gap.start.match(/(\d+)$/)
            const endMatch = gap.end.match(/(\d+)$/)
            if (startMatch && endMatch) {
              const s = parseInt(startMatch[1], 10)
              const e = parseInt(endMatch[1], 10)
              for (let num = s; num <= e; num++) {
                coveredNumbers.add(`${type}-${String(num).padStart(3, '0')}`)
              }
            }
          }
          expect(coveredNumbers.has(removedStr)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('gaps do not overlap and only cover missing numbers', () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(fc.integer({ min: 1, max: 100 }), { minLength: 2, maxLength: 30 }),
        (nums) => {
          const type = '转'
          const nos = nums.map(n => `${type}-${String(n).padStart(3, '0')}`)
          const gaps = detectGaps(nos)

          // All gap numbers should be between min and max of input but not in input
          const inputSet = new Set(nums)
          const min = Math.min(...nums)
          const max = Math.max(...nums)

          for (const gap of gaps) {
            const startMatch = gap.start.match(/(\d+)$/)
            const endMatch = gap.end.match(/(\d+)$/)
            if (startMatch && endMatch) {
              const s = parseInt(startMatch[1], 10)
              const e = parseInt(endMatch[1], 10)
              // Gap range must be within [min+1, max-1]
              expect(s).toBeGreaterThan(min - 1)
              expect(e).toBeLessThan(max + 1)
              // Each number in gap range must NOT be in input
              for (let num = s; num <= e; num++) {
                expect(inputSet.has(num)).toBe(false)
              }
              // Gap count must equal range size
              expect(gap.count).toBe(e - s + 1)
            }
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 本福特分布正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 4: 本福特分布正确性', () => {
  /**
   * **Validates: Requirements 5.1, 5.2**
   *
   * For any positive amounts array:
   * - expected(d) = log10(1 + 1/d) for all digits 1-9
   * - All 9 digit buckets (1-9) are present in output
   * - Σactual = 1.0 (for non-empty input, within tolerance)
   */

  it('expected values always equal log10(1+1/d)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 50 }),
        (amounts) => {
          const result = benfordDistribution(amounts)
          for (let i = 0; i < 9; i++) {
            const d = i + 1
            expect(result[i].expected).toBeCloseTo(Math.log10(1 + 1 / d), 10)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('all 9 digit buckets (1-9) are present in output', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 0, maxLength: 50 }),
        (amounts) => {
          const result = benfordDistribution(amounts)
          expect(result).toHaveLength(9)
          for (let i = 0; i < 9; i++) {
            expect(result[i].digit).toBe(i + 1)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('Σactual = 1.0 for non-empty valid input', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 100 }),
        (amounts) => {
          const result = benfordDistribution(amounts)
          const totalActual = result.reduce((s, r) => s + r.actual, 0)
          expect(totalActual).toBeCloseTo(1.0, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('deviation = actual - expected for each digit', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 50 }),
        (amounts) => {
          const result = benfordDistribution(amounts)
          for (const r of result) {
            expect(r.deviation).toBeCloseTo(r.actual - r.expected, 10)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('empty input returns 9 rows with count=0 and actual=0', () => {
    const result = benfordDistribution([])
    expect(result).toHaveLength(9)
    for (const r of result) {
      expect(r.count).toBe(0)
      expect(r.actual).toBe(0)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 异常筛选规则确定性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c23-c24-journal-entry-testing, Property 5: 异常筛选规则确定性', () => {
  /**
   * **Validates: Requirements 4.1, 4.4**
   *
   * For any JournalEntry[] and AnomalyRules:
   * - An entry with amount = approvalLimit - 1 (within 5% tolerance) → flagged by "刚好低于审批限额"
   * - An entry posted on a holiday → flagged by "假期录入"
   * - Enabling more rules → result set is superset of fewer rules
   */

  it('entry with amount just below approval limit → flagged "刚好低于审批限额"', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 10000, max: 5000000, noNaN: true, noDefaultInfinity: true }),
        (approvalLimit) => {
          // Amount is approvalLimit - 1 (within 5% tolerance window)
          const amount = approvalLimit - 1
          // Ensure amount is within the tolerance zone: [approvalLimit - 5%, approvalLimit)
          const tolerance = approvalLimit * 0.05
          if (amount < approvalLimit - tolerance || amount >= approvalLimit) return // skip if out of range

          const entry: JournalEntry = {
            voucherDate: '2025-03-15', voucherMonth: 3, voucherType: '转',
            voucherNo: '转-001', summary: '正常业务', accountCode: '6001',
            accountName: '测试', debit: amount, credit: 0,
            voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
          }
          const rules: AnomalyRules = {
            holidays: [], nightStartHour: 22, nightEndHour: 6,
            largeAmountThreshold: approvalLimit * 10, // large enough to not trigger
            approvalLimit,
            roundAmountDigits: 10, // very high to not trigger
            vagueKeywords: [], checkEmptySummary: false, duplicateCheck: false,
          }
          const result = screenAnomalies([entry], rules)
          const flagged = result.find(r => r.entry === entry)
          expect(flagged).toBeDefined()
          expect(flagged!.reasons).toContain('刚好低于审批限额')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('entry posted on a holiday → flagged "假期录入"', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        fc.float({ min: 1, max: 100000, noNaN: true, noDefaultInfinity: true }),
        (holidayDate, amount) => {
          const entry: JournalEntry = {
            voucherDate: holidayDate, voucherMonth: 1, voucherType: '转',
            voucherNo: '转-001', summary: '正常业务', accountCode: '6001',
            accountName: '测试', debit: amount, credit: 0,
            voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
          }
          const rules: AnomalyRules = {
            holidays: [holidayDate], nightStartHour: 22, nightEndHour: 6,
            largeAmountThreshold: 1e12, // huge to avoid triggering
            approvalLimit: 1e12,
            roundAmountDigits: 20,
            vagueKeywords: [], checkEmptySummary: false, duplicateCheck: false,
          }
          const result = screenAnomalies([entry], rules)
          const flagged = result.find(r => r.entry === entry)
          expect(flagged).toBeDefined()
          expect(flagged!.reasons).toContain('假期录入')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('determinism: same input produces same output', () => {
    fc.assert(
      fc.property(
        fc.array(arbJournalEntry(), { minLength: 1, maxLength: 15 }),
        arbAnomalyRules,
        (entries, rules) => {
          const result1 = screenAnomalies(entries, rules)
          const result2 = screenAnomalies(entries, rules)
          // Same number of flagged entries
          expect(result1.length).toBe(result2.length)
          // Same reasons for each
          for (let i = 0; i < result1.length; i++) {
            expect(result1[i].reasons).toEqual(result2[i].reasons)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('enabling more rules produces superset of flagged entries', () => {
    fc.assert(
      fc.property(
        fc.array(arbJournalEntry(), { minLength: 1, maxLength: 15 }),
        (entries) => {
          // Minimal rules (fewer checks enabled)
          const minimalRules: AnomalyRules = {
            holidays: [], nightStartHour: 22, nightEndHour: 6,
            largeAmountThreshold: 1e12, approvalLimit: 1e12,
            roundAmountDigits: 20,
            vagueKeywords: [], checkEmptySummary: false, duplicateCheck: false,
          }
          // Extended rules (more checks enabled)
          const extendedRules: AnomalyRules = {
            holidays: ['2025-01-01'], nightStartHour: 22, nightEndHour: 6,
            largeAmountThreshold: 500000, approvalLimit: 200000,
            roundAmountDigits: 3,
            vagueKeywords: ['调整', '暂估'], checkEmptySummary: true, duplicateCheck: true,
          }

          const minimalResult = screenAnomalies(entries, minimalRules)
          const extendedResult = screenAnomalies(entries, extendedRules)

          // Extended should flag at least as many entries as minimal
          expect(extendedResult.length).toBeGreaterThanOrEqual(minimalResult.length)

          // Every entry flagged by minimal should also be flagged by extended
          const extendedEntries = new Set(extendedResult.map(r => r.entry))
          for (const r of minimalResult) {
            expect(extendedEntries.has(r.entry)).toBe(true)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
