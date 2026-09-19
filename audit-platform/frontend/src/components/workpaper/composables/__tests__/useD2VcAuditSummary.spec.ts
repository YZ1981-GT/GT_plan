/**
 * useD2VcAuditSummary — Unit Tests
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 4.1
 *
 * Tests the computeAuditSummary pure function exported from useD2VcAuditSummary.ts
 *
 * Validates: Requirements 9.1, 9.2
 */
import { describe, it, expect } from 'vitest'
import { computeAuditSummary, type AuditSummaryStats } from '../useD2VcAuditSummary'
import type { VoucherCheckRow } from '../useD2VoucherCheckEnhanced'

// ─── Helper ──────────────────────────────────────────────────────────────────

function makeRow(overrides: Partial<VoucherCheckRow> = {}): VoucherCheckRow {
  return {
    rowId: `test-${Math.random().toString(36).slice(2)}`,
    seq: 1,
    customerName: '',
    voucherDate: '',
    voucherNo: '',
    businessContent: '',
    counterpartAccount: '',
    counterpartDetail: '',
    debitAmount: 0,
    creditAmount: 0,
    supportingDoc: '',
    check1: '',
    check2: '',
    check3: '',
    check4: '',
    check5: '',
    indexRef: '',
    isAbnormal: '',
    remark: '',
    attachments: [],
    ...overrides,
  }
}

// ─── computeAuditSummary ─────────────────────────────────────────────────────

describe('computeAuditSummary', () => {
  it('should return all zeros for empty rows', () => {
    const result = computeAuditSummary([], [], 100000)
    expect(result).toEqual<AuditSummaryStats>({
      occurrenceAmount: 100000,
      checkedAmount: 0,
      coverageRatio: 0,
      checkedCount: 0,
      abnormalCount: 0,
      abnormalAmount: 0,
      abnormalRate: 0,
    })
  })

  it('should compute checkedAmount as sum of debit+credit across both zones', () => {
    const current = [
      makeRow({ debitAmount: 1000, creditAmount: 200 }),
      makeRow({ debitAmount: 500, creditAmount: 300 }),
    ]
    const post = [
      makeRow({ debitAmount: 2000, creditAmount: 0 }),
    ]
    const result = computeAuditSummary(current, post, 10000)
    // 1000+200 + 500+300 + 2000+0 = 4000
    expect(result.checkedAmount).toBe(4000)
  })

  it('should compute checkedCount as total rows across both zones', () => {
    const current = [makeRow(), makeRow(), makeRow()]
    const post = [makeRow(), makeRow()]
    const result = computeAuditSummary(current, post, 10000)
    expect(result.checkedCount).toBe(5)
  })

  it('should compute abnormalCount from rows with non-empty isAbnormal', () => {
    const current = [
      makeRow({ isAbnormal: '金额异常' }),
      makeRow({ isAbnormal: '' }),
      makeRow({ isAbnormal: '跨期疑点' }),
    ]
    const post = [
      makeRow({ isAbnormal: '   ' }), // whitespace only → not abnormal
    ]
    const result = computeAuditSummary(current, post, 10000)
    expect(result.abnormalCount).toBe(2)
  })

  it('should compute abnormalAmount from abnormal rows only', () => {
    const current = [
      makeRow({ debitAmount: 5000, creditAmount: 0, isAbnormal: '金额异常' }),
      makeRow({ debitAmount: 3000, creditAmount: 0, isAbnormal: '' }),
    ]
    const post = [
      makeRow({ debitAmount: 1000, creditAmount: 500, isAbnormal: '跨期疑点' }),
    ]
    const result = computeAuditSummary(current, post, 10000)
    // abnormal: 5000+0 + 1000+500 = 6500
    expect(result.abnormalAmount).toBe(6500)
  })

  it('should compute abnormalRate as abnormalCount/checkedCount*100', () => {
    const rows = [
      makeRow({ isAbnormal: '异常' }),
      makeRow({ isAbnormal: '' }),
      makeRow({ isAbnormal: '' }),
      makeRow({ isAbnormal: '异常' }),
    ]
    const result = computeAuditSummary(rows, [], 10000)
    // 2/4 * 100 = 50%
    expect(result.abnormalRate).toBe(50)
  })

  it('should return 0 abnormalRate when no rows exist', () => {
    const result = computeAuditSummary([], [], 10000)
    expect(result.abnormalRate).toBe(0)
  })

  it('should compute coverageRatio as checkedAmount/occurrenceAmount*100', () => {
    const rows = [
      makeRow({ debitAmount: 2500, creditAmount: 0 }),
      makeRow({ debitAmount: 2500, creditAmount: 0 }),
    ]
    const result = computeAuditSummary(rows, [], 10000)
    // 5000 / 10000 * 100 = 50%
    expect(result.coverageRatio).toBe(50)
  })

  it('should return 0 coverageRatio when occurrenceAmount is 0', () => {
    const rows = [makeRow({ debitAmount: 1000, creditAmount: 0 })]
    const result = computeAuditSummary(rows, [], 0)
    expect(result.coverageRatio).toBe(0)
  })

  it('should pass through occurrenceAmount unchanged', () => {
    const result = computeAuditSummary([], [], 99999)
    expect(result.occurrenceAmount).toBe(99999)
  })

  it('should handle rows with NaN/undefined amounts gracefully', () => {
    const rows = [
      makeRow({ debitAmount: NaN, creditAmount: undefined as any }),
      makeRow({ debitAmount: 1000, creditAmount: 0 }),
    ]
    const result = computeAuditSummary(rows, [], 10000)
    // NaN||0 = 0, undefined||0 = 0 → first row contributes 0
    expect(result.checkedAmount).toBe(1000)
  })

  it('should trim isAbnormal before checking emptiness', () => {
    const rows = [
      makeRow({ isAbnormal: '  \t  ' }), // whitespace only → not abnormal
      makeRow({ isAbnormal: ' 异常 ' }), // has content after trim → abnormal
    ]
    const result = computeAuditSummary(rows, [], 10000)
    expect(result.abnormalCount).toBe(1)
  })
})
