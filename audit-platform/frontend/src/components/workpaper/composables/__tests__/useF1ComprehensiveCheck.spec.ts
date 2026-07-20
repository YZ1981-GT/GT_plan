/**
 * useF1ComprehensiveCheck 纯函数单测 — F1-7 检查比例 / 异常 / 重点样本
 */
import { describe, expect, it } from 'vitest'
import {
  calcCoverageRatio,
  migrateLegacyCurrentRows,
  computeAnomalyRate,
  isAbnormalFlag,
  selectPrioritySamplesFromDetail,
  evaluateF1DebitEvidence,
  evaluateF1CreditEvidence,
  f1EvidenceStatusLabel,
  createEmptyDebitRow,
  createEmptyCreditRow,
  shouldMarkCrossPeriod,
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

  it('isAbnormalFlag ignores N/否/无异常', () => {
    expect(isAbnormalFlag('')).toBe(false)
    expect(isAbnormalFlag('N')).toBe(false)
    expect(isAbnormalFlag('否')).toBe(false)
    expect(isAbnormalFlag('无异常')).toBe(false)
    expect(isAbnormalFlag('金额不符')).toBe(true)
    expect(isAbnormalFlag('跨期疑点')).toBe(true)
  })

  it('computeAnomalyRate excludes non-abnormal markers', () => {
    expect(computeAnomalyRate([
      { isAbnormal: '' },
      { isAbnormal: 'N' },
      { isAbnormal: '金额不符' },
      { isAbnormal: '跨期疑点' },
    ])).toBe(50)
  })

  it('selectPrioritySamplesFromDetail picks related / over-1y / large', () => {
    const picked = selectPrioritySamplesFromDetail([
      { customerName: '关联甲', endAudited: 100, debit: 80, relationType: '母公司' },
      { customerName: '长账龄乙', endAudited: 200, debit: 50, agingAudited: { y1to2: 200 } },
      { customerName: '普通丙', endAudited: 10, debit: 10, relationType: '非关联方', agingAudited: { within1: 10 } },
      { customerName: '大额丁', endAudited: 9000, debit: 9000 },
    ], { topN: 2 })
    const names = picked.map(p => p.supplierName)
    expect(names).toContain('关联甲')
    expect(names).toContain('长账龄乙')
    expect(names).toContain('大额丁')
    expect(names).not.toContain('普通丙')
    expect(picked.find(p => p.supplierName === '关联甲')!.reason).toMatch(/关联方/)
  })

  it('evaluateF1DebitEvidence flags missing bank / amount mismatch', () => {
    const empty = evaluateF1DebitEvidence(createEmptyDebitRow())
    expect(empty.find(c => c.key === 'voucher')!.status).toBe('missing')
    expect(f1EvidenceStatusLabel(empty).type).toBe('warning')

    const mismatch = evaluateF1DebitEvidence({
      ...createEmptyDebitRow(),
      supplierName: '甲',
      voucherNo: '记-1',
      debitAmount: 1000,
      approvalDateNo: '2024-01-01',
      approvalOk: 'Y',
      bankPayee: '甲',
      bankAmount: 900,
      contractName: '合同A',
      contractAmount: 1000,
    })
    expect(mismatch.find(c => c.key === 'bank')!.status).toBe('mismatch')
    expect(f1EvidenceStatusLabel(mismatch).type).toBe('danger')
  })

  it('evaluateF1CreditEvidence completes when recv + invoice match', () => {
    const ok = evaluateF1CreditEvidence({
      ...createEmptyCreditRow(),
      supplierName: '乙',
      voucherNo: '记-2',
      creditAmount: 500,
      recvDateNo: '2024-02-01',
      recvItemName: '材料',
      invoiceDateNo: '2024-02-02',
      invoiceCounterparty: '乙',
      invoiceAmount: 500,
    })
    expect(ok.every(c => c.status === 'ok')).toBe(true)
    expect(f1EvidenceStatusLabel(ok).label).toBe('勾稽完成')
  })

  it('shouldMarkCrossPeriod when voucher before cutoff', () => {
    expect(shouldMarkCrossPeriod(new Date('2024-12-30'), new Date('2024-12-31'))).toBe(true)
    expect(shouldMarkCrossPeriod(new Date('2025-01-02'), new Date('2024-12-31'))).toBe(false)
  })
})
