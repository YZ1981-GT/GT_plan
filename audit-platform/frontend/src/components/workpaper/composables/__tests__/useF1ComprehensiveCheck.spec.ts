import { describe, expect, it } from 'vitest'
import {
  calcCoverageRatio,
  migrateLegacyCurrentRows,
  computeAnomalyRate,
} from '../useF1ComprehensiveCheck'

describe('useF1ComprehensiveCheck pure helpers', () => {
  it('calcCoverageRatio returns null when book is zero', () => {
    expect(calcCoverageRatio(100, 0)).toBeNull()
  })

  it('calcCoverageRatio rounds to two decimals', () => {
    expect(calcCoverageRatio(1, 3)).toBe(33.33)
    expect(calcCoverageRatio(2, 3)).toBe(66.67)
  })

  it('migrateLegacyCurrentRows splits debit and credit rows', () => {
    const legacy = JSON.stringify([
      {
        rowId: 'a',
        customerName: '甲公司',
        debitAmount: 1000,
        creditAmount: 0,
        voucherNo: '记-1',
      },
      {
        rowId: 'b',
        customerName: '乙公司',
        debitAmount: 0,
        creditAmount: 500,
        supportingDoc: '发票',
      },
      {
        rowId: 'c',
        customerName: '空行',
        debitAmount: 0,
        creditAmount: 0,
      },
    ])
    const { debit, credit } = migrateLegacyCurrentRows(legacy)
    expect(debit).toHaveLength(2)
    expect(credit).toHaveLength(1)
    expect(debit[0].supplierName).toBe('甲公司')
    expect(debit[0].debitAmount).toBe(1000)
    expect(credit[0].supplierName).toBe('乙公司')
    expect(credit[0].creditAmount).toBe(500)
    expect(credit[0].remark).toBe('发票')
  })

  it('computeAnomalyRate counts non-empty isAbnormal', () => {
    expect(computeAnomalyRate([
      { isAbnormal: '' },
      { isAbnormal: '金额不符' },
    ])).toBe(50)
  })
})
