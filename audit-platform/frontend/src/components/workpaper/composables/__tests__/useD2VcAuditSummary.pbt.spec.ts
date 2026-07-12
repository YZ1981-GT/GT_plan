/**
 * Property-Based Tests — D2-7 审计说明统计自动化 composable
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 4.2
 *
 * 使用 fast-check + vitest 验证 Property 13: Audit summary statistics correctness。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { computeAuditSummary } from '../useD2VcAuditSummary'
import type { VoucherCheckRow } from '../useD2VoucherCheckEnhanced'

// ─── Generators ──────────────────────────────────────────────────────────────

/**
 * 生成任意 VoucherCheckRow，仅关注统计计算所需字段：
 * debitAmount, creditAmount, isAbnormal
 * 其余字段填充合理默认值
 */
const arbVoucherCheckRow: fc.Arbitrary<VoucherCheckRow> = fc.record({
  rowId: fc.uuid(),
  seq: fc.nat({ max: 999 }),
  customerName: fc.string({ maxLength: 10 }),
  voucherDate: fc.constantFrom('2025-01-15', '2025-06-30', '2025-12-31', ''),
  voucherNo: fc.string({ minLength: 1, maxLength: 10 }),
  businessContent: fc.string({ maxLength: 20 }),
  counterpartAccount: fc.string({ maxLength: 10 }),
  counterpartDetail: fc.string({ maxLength: 10 }),
  debitAmount: fc.oneof(
    fc.integer({ min: 0, max: 10000000 }),
    fc.double({ min: 0, max: 10000000, noNaN: true, noDefaultInfinity: true }),
  ),
  creditAmount: fc.oneof(
    fc.integer({ min: 0, max: 10000000 }),
    fc.double({ min: 0, max: 10000000, noNaN: true, noDefaultInfinity: true }),
  ),
  supportingDoc: fc.string({ maxLength: 5 }),
  check1: fc.string({ maxLength: 5 }),
  check2: fc.string({ maxLength: 5 }),
  check3: fc.string({ maxLength: 5 }),
  check4: fc.string({ maxLength: 5 }),
  check5: fc.string({ maxLength: 5 }),
  indexRef: fc.string({ maxLength: 5 }),
  isAbnormal: fc.constantFrom('', '  ', '金额异常', '跨期疑点', '关联交易'),
  remark: fc.string({ maxLength: 10 }),
  attachments: fc.constant([]),
  ocrResult: fc.constant(undefined),
  source: fc.constantFrom(undefined, '手动', '抽凭'),
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 13: Audit summary statistics correctness
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 13: Audit summary statistics correctness', () => {
  /**
   * **Validates: Requirements 9.1, 9.2**
   *
   * For any set of VoucherCheckRows across both zones, the computed audit summary satisfies:
   * - checkedAmount == sum(debitAmount + creditAmount) over all rows
   * - checkedCount == total number of rows across both zones
   * - abnormalCount == count of rows where isAbnormal is truthy (non-empty after trim)
   * - abnormalRate == abnormalCount / checkedCount * 100 (or 0 if no rows)
   * - coverageRatio == checkedAmount / occurrenceAmount * 100 (or 0 if occurrenceAmount is 0)
   */

  it('checkedAmount equals sum of (debitAmount + creditAmount) across both zones', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),  // currentRows
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),  // postRows
        fc.double({ min: 0, max: 100000000, noNaN: true, noDefaultInfinity: true }),  // occurrenceAmount
        (currentRows, postRows, occurrenceAmount) => {
          const result = computeAuditSummary(currentRows, postRows, occurrenceAmount)

          // Independently compute expected checkedAmount
          const allRows = [...currentRows, ...postRows]
          let expectedCheckedAmount = 0
          for (const row of allRows) {
            expectedCheckedAmount += (Number(row.debitAmount) || 0) + (Number(row.creditAmount) || 0)
          }

          expect(result.checkedAmount).toBeCloseTo(expectedCheckedAmount, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('checkedCount equals total number of rows across both zones', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.double({ min: 0, max: 100000000, noNaN: true, noDefaultInfinity: true }),
        (currentRows, postRows, occurrenceAmount) => {
          const result = computeAuditSummary(currentRows, postRows, occurrenceAmount)

          const expectedCount = currentRows.length + postRows.length
          expect(result.checkedCount).toBe(expectedCount)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('abnormalCount equals count of rows where isAbnormal is truthy (non-empty after trim)', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.double({ min: 0, max: 100000000, noNaN: true, noDefaultInfinity: true }),
        (currentRows, postRows, occurrenceAmount) => {
          const result = computeAuditSummary(currentRows, postRows, occurrenceAmount)

          const allRows = [...currentRows, ...postRows]
          const expectedAbnormalCount = allRows.filter(
            r => r.isAbnormal && r.isAbnormal.trim() !== '',
          ).length

          expect(result.abnormalCount).toBe(expectedAbnormalCount)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('abnormalRate == abnormalCount / checkedCount * 100 (or 0 if no rows)', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.double({ min: 0, max: 100000000, noNaN: true, noDefaultInfinity: true }),
        (currentRows, postRows, occurrenceAmount) => {
          const result = computeAuditSummary(currentRows, postRows, occurrenceAmount)

          const allRows = [...currentRows, ...postRows]
          const checkedCount = allRows.length
          const abnormalCount = allRows.filter(
            r => r.isAbnormal && r.isAbnormal.trim() !== '',
          ).length

          const expectedRate = checkedCount > 0
            ? (abnormalCount / checkedCount) * 100
            : 0

          expect(result.abnormalRate).toBeCloseTo(expectedRate, 10)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('coverageRatio == checkedAmount / occurrenceAmount * 100 (or 0 if occurrenceAmount is 0)', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 20 }),
        fc.double({ min: 0, max: 100000000, noNaN: true, noDefaultInfinity: true }),
        (currentRows, postRows, occurrenceAmount) => {
          const result = computeAuditSummary(currentRows, postRows, occurrenceAmount)

          const allRows = [...currentRows, ...postRows]
          let checkedAmount = 0
          for (const row of allRows) {
            checkedAmount += (Number(row.debitAmount) || 0) + (Number(row.creditAmount) || 0)
          }

          const expectedRatio = occurrenceAmount > 0
            ? (checkedAmount / occurrenceAmount) * 100
            : 0

          expect(result.coverageRatio).toBeCloseTo(expectedRatio, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('occurrenceAmount in result equals the input occurrenceAmount', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 10 }),
        fc.array(arbVoucherCheckRow, { minLength: 0, maxLength: 10 }),
        fc.double({ min: 0, max: 100000000, noNaN: true, noDefaultInfinity: true }),
        (currentRows, postRows, occurrenceAmount) => {
          const result = computeAuditSummary(currentRows, postRows, occurrenceAmount)
          expect(result.occurrenceAmount).toBe(occurrenceAmount)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('empty rows produce zero statistics', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 100000000, noNaN: true, noDefaultInfinity: true }),
        (occurrenceAmount) => {
          const result = computeAuditSummary([], [], occurrenceAmount)

          expect(result.checkedAmount).toBe(0)
          expect(result.checkedCount).toBe(0)
          expect(result.abnormalCount).toBe(0)
          expect(result.abnormalAmount).toBe(0)
          expect(result.abnormalRate).toBe(0)
          expect(result.coverageRatio).toBe(0)
          expect(result.occurrenceAmount).toBe(occurrenceAmount)
        },
      ),
      { numRuns: 100 },
    )
  })
})
