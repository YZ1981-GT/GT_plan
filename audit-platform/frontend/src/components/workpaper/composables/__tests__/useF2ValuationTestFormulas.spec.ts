import { describe, it, expect } from 'vitest'
import { enrichValuationTestRow } from '../useF2ValuationTestFormulas'
import { calcInspectionCoverage } from '../useF2InspectionCheckFormulas'

describe('useF2ValuationTestFormulas', () => {
  it('weighted-avg auditIssueAmt = unitPrice × issueQty', () => {
    const row = enrichValuationTestRow({
      rowId: '1', seq: 1, voucherNo: '', itemName: 'A',
      openingQty: 10, openingAmt: 100, inboundQty: 10, inboundAmt: 120,
      issueQty: 5, bookIssueAmt: 50, fifoUnitPrice: 0,
      stdPrice: 0, stdQty: 0, actPrice: 0, actQty: 0,
      auditIssueAmt: 0, varianceAmt: 0, varianceRate: '',
    }, 'weighted-avg')
    expect(row.auditIssueAmt).toBe(55)
  })

  it('fifo uses fifoUnitPrice × issueQty', () => {
    const row = enrichValuationTestRow({
      rowId: '1', seq: 1, voucherNo: '', itemName: 'A',
      openingQty: 0, openingAmt: 0, inboundQty: 0, inboundAmt: 0,
      issueQty: 10, bookIssueAmt: 100, fifoUnitPrice: 12,
      stdPrice: 0, stdQty: 0, actPrice: 0, actQty: 0,
      auditIssueAmt: 0, varianceAmt: 0, varianceRate: '',
    }, 'fifo')
    expect(row.auditIssueAmt).toBe(120)
  })
})

describe('useF2InspectionCheckFormulas', () => {
  it('coverage = checked / book × 100', () => {
    expect(calcInspectionCoverage(500, 1000)).toBe(50)
  })
})
