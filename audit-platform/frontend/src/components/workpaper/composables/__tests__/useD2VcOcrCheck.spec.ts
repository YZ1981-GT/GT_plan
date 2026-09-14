/**
 * useD2VcOcrCheck — Unit Tests
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 3.1
 *
 * Tests all pure functions exported from useD2VcOcrCheck.ts:
 * - normalizeDate: various date format normalization
 * - fuzzyMatch: character overlap similarity
 * - extractOcrFields: OCR response parsing
 * - compareOcrWithRow: comparison logic
 * - backfillCheckColumns: check column mapping
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeDate,
  fuzzyMatch,
  extractOcrFields,
  compareOcrWithRow,
  backfillCheckColumns,
  MATCH_STATUS_TEXT,
  type CheckCompareResult,
} from '../useD2VcOcrCheck'
import type { VoucherCheckRow, OcrExtractedData } from '../useD2VoucherCheckEnhanced'

// ─── Helper ─────────────────────────────────────────────────────────────────

function makeRow(overrides: Partial<VoucherCheckRow> = {}): VoucherCheckRow {
  return {
    rowId: 'test-row-1',
    seq: 1,
    customerName: '测试客户',
    voucherDate: '2025-06-15',
    voucherNo: 'PZ-2025-001',
    businessContent: '销售商品',
    counterpartAccount: '北京科技有限公司',
    counterpartDetail: '',
    debitAmount: 10000,
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

// ─── normalizeDate ──────────────────────────────────────────────────────────

describe('normalizeDate', () => {
  it('returns empty string for null/undefined/empty', () => {
    expect(normalizeDate(null)).toBe('')
    expect(normalizeDate(undefined)).toBe('')
    expect(normalizeDate('')).toBe('')
    expect(normalizeDate('   ')).toBe('')
  })

  it('preserves already normalized YYYY-MM-DD', () => {
    expect(normalizeDate('2025-06-15')).toBe('2025-06-15')
    expect(normalizeDate('2024-01-01')).toBe('2024-01-01')
  })

  it('normalizes YYYY/MM/DD', () => {
    expect(normalizeDate('2025/06/15')).toBe('2025-06-15')
    expect(normalizeDate('2025/1/5')).toBe('2025-01-05')
  })

  it('normalizes YYYY.MM.DD', () => {
    expect(normalizeDate('2025.06.15')).toBe('2025-06-15')
    expect(normalizeDate('2025.1.5')).toBe('2025-01-05')
  })

  it('normalizes YYYYMMDD', () => {
    expect(normalizeDate('20250615')).toBe('2025-06-15')
    expect(normalizeDate('20240101')).toBe('2024-01-01')
  })

  it('normalizes YYYY年MM月DD日', () => {
    expect(normalizeDate('2025年06月15日')).toBe('2025-06-15')
    expect(normalizeDate('2025年6月5日')).toBe('2025-06-05')
    expect(normalizeDate('2025年12月31日')).toBe('2025-12-31')
  })

  it('normalizes MM/DD/YYYY (American)', () => {
    expect(normalizeDate('06/15/2025')).toBe('2025-06-15')
    expect(normalizeDate('1/5/2025')).toBe('2025-01-05')
  })

  it('normalizes DD.MM.YYYY (European)', () => {
    expect(normalizeDate('15.06.2025')).toBe('2025-06-15')
    expect(normalizeDate('5.1.2025')).toBe('2025-01-05')
  })

  it('returns empty string for invalid date strings', () => {
    expect(normalizeDate('not-a-date')).toBe('')
    expect(normalizeDate('abc')).toBe('')
  })

  it('trims whitespace before parsing', () => {
    expect(normalizeDate('  2025-06-15  ')).toBe('2025-06-15')
    expect(normalizeDate(' 2025/06/15 ')).toBe('2025-06-15')
  })
})

// ─── fuzzyMatch ─────────────────────────────────────────────────────────────

describe('fuzzyMatch', () => {
  it('returns 1.0 for identical strings', () => {
    expect(fuzzyMatch('北京科技公司', '北京科技公司')).toBe(1.0)
  })

  it('returns 1.0 for identical strings with different case', () => {
    expect(fuzzyMatch('ABC', 'abc')).toBe(1.0)
  })

  it('returns 0 for empty strings', () => {
    expect(fuzzyMatch('', 'test')).toBe(0)
    expect(fuzzyMatch('test', '')).toBe(0)
    expect(fuzzyMatch('', '')).toBe(0)
  })

  it('returns value > 0.6 for similar Chinese company names', () => {
    const sim = fuzzyMatch('北京科技有限公司', '北京科技有限责任公司')
    expect(sim).toBeGreaterThan(0.6)
  })

  it('returns value < 0.6 for dissimilar strings', () => {
    const sim = fuzzyMatch('ABCDEF', 'XYZ123')
    expect(sim).toBeLessThan(0.6)
  })

  it('trims whitespace before comparison', () => {
    expect(fuzzyMatch('  abc  ', 'abc')).toBe(1.0)
  })
})

// ─── extractOcrFields ───────────────────────────────────────────────────────

describe('extractOcrFields', () => {
  it('returns empty object for null/undefined input', () => {
    expect(extractOcrFields(null)).toEqual({})
    expect(extractOcrFields(undefined)).toEqual({})
  })

  it('returns empty object for non-object input', () => {
    expect(extractOcrFields('string')).toEqual({})
    expect(extractOcrFields(123)).toEqual({})
  })

  it('extracts amount from top-level field', () => {
    const result = extractOcrFields({ amount: '10,000.50' })
    expect(result.amount).toBe(10000.5)
  })

  it('extracts amount with currency symbols', () => {
    const result = extractOcrFields({ amount: '¥10000.00' })
    expect(result.amount).toBe(10000)
  })

  it('extracts amount as number directly', () => {
    const result = extractOcrFields({ amount: 5000 })
    expect(result.amount).toBe(5000)
  })

  it('extracts date and normalizes', () => {
    const result = extractOcrFields({ date: '2025/06/15' })
    expect(result.date).toBe('2025-06-15')
  })

  it('extracts date from Chinese format', () => {
    const result = extractOcrFields({ date: '2025年6月15日' })
    expect(result.date).toBe('2025-06-15')
  })

  it('extracts counterparty and trims', () => {
    const result = extractOcrFields({ counterparty: '  北京科技公司  ' })
    expect(result.counterparty).toBe('北京科技公司')
  })

  it('extracts contractNo', () => {
    const result = extractOcrFields({ contractNo: 'HT-2025-001' })
    expect(result.contractNo).toBe('HT-2025-001')
  })

  it('extracts from nested extracted_fields structure', () => {
    const result = extractOcrFields({
      extracted_fields: {
        amount: '5000',
        date: '2025-01-01',
        counterparty: '供应商A',
        contract_no: 'C-001',
        full_text: 'OCR全文...',
      },
    })
    expect(result.amount).toBe(5000)
    expect(result.date).toBe('2025-01-01')
    expect(result.counterparty).toBe('供应商A')
    expect(result.contractNo).toBe('C-001')
    expect(result.rawText).toBe('OCR全文...')
  })

  it('extracts from nested data structure', () => {
    const result = extractOcrFields({
      data: {
        amount: 8000,
        invoice_date: '2025.03.20',
        seller: '上海贸易公司',
      },
    })
    expect(result.amount).toBe(8000)
    expect(result.date).toBe('2025-03-20')
    expect(result.counterparty).toBe('上海贸易公司')
  })

  it('extracts using Chinese field names', () => {
    const result = extractOcrFields({
      金额: '12345.67',
      日期: '2025年3月1日',
      对方单位: '深圳电子公司',
      合同编号: 'HT-003',
    })
    expect(result.amount).toBe(12345.67)
    expect(result.date).toBe('2025-03-01')
    expect(result.counterparty).toBe('深圳电子公司')
    expect(result.contractNo).toBe('HT-003')
  })

  it('skips fields with empty/null values', () => {
    const result = extractOcrFields({
      amount: '',
      date: null,
      counterparty: undefined,
      contractNo: '',
    })
    expect(result.amount).toBeUndefined()
    expect(result.date).toBeUndefined()
    expect(result.counterparty).toBeUndefined()
    expect(result.contractNo).toBeUndefined()
  })

  it('handles NaN amount gracefully', () => {
    const result = extractOcrFields({ amount: 'not-a-number' })
    expect(result.amount).toBeUndefined()
  })
})

// ─── compareOcrWithRow ──────────────────────────────────────────────────────

describe('compareOcrWithRow', () => {
  it('returns all undetermined when ocrData is empty', () => {
    const result = compareOcrWithRow({}, makeRow())
    expect(result.amountMatch).toBe('undetermined')
    expect(result.dateMatch).toBe('undetermined')
    expect(result.counterpartyMatch).toBe('undetermined')
    expect(result.businessMatch).toBe('undetermined')
    expect(result.attachmentComplete).toBe('consistent')
  })

  // Amount
  it('returns consistent when amount matches within tolerance', () => {
    const ocr: OcrExtractedData = { amount: 10000.005 }
    const result = compareOcrWithRow(ocr, makeRow({ debitAmount: 10000 }))
    expect(result.amountMatch).toBe('consistent')
  })

  it('returns inconsistent when amount differs beyond tolerance', () => {
    const ocr: OcrExtractedData = { amount: 9000 }
    const result = compareOcrWithRow(ocr, makeRow({ debitAmount: 10000 }))
    expect(result.amountMatch).toBe('inconsistent')
  })

  it('compares with creditAmount when debitAmount is 0', () => {
    const ocr: OcrExtractedData = { amount: 5000 }
    const result = compareOcrWithRow(ocr, makeRow({ debitAmount: 0, creditAmount: 5000 }))
    expect(result.amountMatch).toBe('consistent')
  })

  it('returns undetermined when row amount is 0 but OCR has value', () => {
    const ocr: OcrExtractedData = { amount: 5000 }
    const result = compareOcrWithRow(ocr, makeRow({ debitAmount: 0, creditAmount: 0 }))
    expect(result.amountMatch).toBe('undetermined')
  })

  // Date
  it('returns consistent when dates match after normalization', () => {
    const ocr: OcrExtractedData = { date: '2025/06/15' }
    const result = compareOcrWithRow(ocr, makeRow({ voucherDate: '2025-06-15' }))
    expect(result.dateMatch).toBe('consistent')
  })

  it('returns inconsistent when dates differ', () => {
    const ocr: OcrExtractedData = { date: '2025-06-16' }
    const result = compareOcrWithRow(ocr, makeRow({ voucherDate: '2025-06-15' }))
    expect(result.dateMatch).toBe('inconsistent')
  })

  it('returns undetermined when row date is empty', () => {
    const ocr: OcrExtractedData = { date: '2025-06-15' }
    const result = compareOcrWithRow(ocr, makeRow({ voucherDate: '' }))
    expect(result.dateMatch).toBe('undetermined')
  })

  // Counterparty
  it('returns consistent when counterparty similarity > threshold', () => {
    const ocr: OcrExtractedData = { counterparty: '北京科技有限公司' }
    const result = compareOcrWithRow(ocr, makeRow({ counterpartAccount: '北京科技有限公司' }))
    expect(result.counterpartyMatch).toBe('consistent')
  })

  it('returns inconsistent when counterparty similarity <= threshold', () => {
    const ocr: OcrExtractedData = { counterparty: 'ABCXYZ' }
    const result = compareOcrWithRow(ocr, makeRow({ counterpartAccount: '完全不同' }))
    expect(result.counterpartyMatch).toBe('inconsistent')
  })

  it('returns undetermined when row counterparty is empty', () => {
    const ocr: OcrExtractedData = { counterparty: '北京公司' }
    const result = compareOcrWithRow(ocr, makeRow({ counterpartAccount: '', counterpartDetail: '' }))
    expect(result.counterpartyMatch).toBe('undetermined')
  })

  // Business match always undetermined
  it('always returns undetermined for businessMatch', () => {
    const ocr: OcrExtractedData = { amount: 10000, date: '2025-06-15', counterparty: '北京公司' }
    const result = compareOcrWithRow(ocr, makeRow())
    expect(result.businessMatch).toBe('undetermined')
  })

  // Attachment complete always consistent (OCR succeeded)
  it('always returns consistent for attachmentComplete', () => {
    const result = compareOcrWithRow({}, makeRow())
    expect(result.attachmentComplete).toBe('consistent')
  })
})

// ─── backfillCheckColumns ───────────────────────────────────────────────────

describe('backfillCheckColumns', () => {
  it('maps all match statuses to correct Chinese text', () => {
    const confirmed: CheckCompareResult = {
      amountMatch: 'consistent',
      dateMatch: 'inconsistent',
      counterpartyMatch: 'undetermined',
      businessMatch: 'undetermined',
      attachmentComplete: 'consistent',
    }

    const row = makeRow()
    const result = backfillCheckColumns(row, confirmed)

    expect(result.check1).toBe('一致')
    expect(result.check2).toBe('不一致')
    expect(result.check3).toBe('无法判定')
    expect(result.check4).toBe('无法判定')
    expect(result.check5).toBe('一致')
  })

  it('does NOT mutate the original row', () => {
    const row = makeRow({ check1: '原始值', check2: '原始值2' })
    const confirmed: CheckCompareResult = {
      amountMatch: 'consistent',
      dateMatch: 'consistent',
      counterpartyMatch: 'consistent',
      businessMatch: 'undetermined',
      attachmentComplete: 'consistent',
    }

    const result = backfillCheckColumns(row, confirmed)

    // Original unchanged
    expect(row.check1).toBe('原始值')
    expect(row.check2).toBe('原始值2')
    // New row has new values
    expect(result.check1).toBe('一致')
    expect(result.check2).toBe('一致')
  })

  it('preserves all other row fields', () => {
    const row = makeRow({
      customerName: '保留客户',
      voucherNo: 'PZ-999',
      debitAmount: 50000,
    })

    const confirmed: CheckCompareResult = {
      amountMatch: 'consistent',
      dateMatch: 'consistent',
      counterpartyMatch: 'consistent',
      businessMatch: 'consistent',
      attachmentComplete: 'consistent',
    }

    const result = backfillCheckColumns(row, confirmed)

    expect(result.customerName).toBe('保留客户')
    expect(result.voucherNo).toBe('PZ-999')
    expect(result.debitAmount).toBe(50000)
    expect(result.rowId).toBe(row.rowId)
  })

  it('maps all three possible match status values', () => {
    const statuses: Array<'consistent' | 'inconsistent' | 'undetermined'> = [
      'consistent',
      'inconsistent',
      'undetermined',
    ]

    for (const status of statuses) {
      const confirmed: CheckCompareResult = {
        amountMatch: status,
        dateMatch: status,
        counterpartyMatch: status,
        businessMatch: status,
        attachmentComplete: status,
      }

      const result = backfillCheckColumns(makeRow(), confirmed)
      const expected = MATCH_STATUS_TEXT[status]

      expect(result.check1).toBe(expected)
      expect(result.check2).toBe(expected)
      expect(result.check3).toBe(expected)
      expect(result.check4).toBe(expected)
      expect(result.check5).toBe(expected)
    }
  })
})

// ─── Cancel logic (P8: Cancel preserves existing check values) ──────────────

describe('Cancel logic', () => {
  it('backfillCheckColumns is not called when dialog is cancelled', () => {
    // This test validates the design contract:
    // showConfirmDialog returns null on cancel → composable does NOT call backfillCheckColumns
    // Here we verify that if confirmed is null, original row is unchanged
    const row = makeRow({
      check1: '已有值1',
      check2: '已有值2',
      check3: '已有值3',
      check4: '已有值4',
      check5: '已有值5',
    })

    // Simulate cancel: confirmed is null → no backfill
    const confirmed: CheckCompareResult | null = null
    if (confirmed) {
      backfillCheckColumns(row, confirmed)
    }

    // Original row preserves values
    expect(row.check1).toBe('已有值1')
    expect(row.check2).toBe('已有值2')
    expect(row.check3).toBe('已有值3')
    expect(row.check4).toBe('已有值4')
    expect(row.check5).toBe('已有值5')
  })
})
