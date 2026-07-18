/**
 * useF3VoucherCheck.spec — F3-7 应付票据检查表
 * 覆盖：单据勾稽、检查比例、空行修剪、旧数据迁移、区分证据模式
 */
import { describe, it, expect } from 'vitest'
import {
  emptyVoucherRow,
  isBlankVoucherRow,
  evaluateF3VoucherEvidence,
  sectionEvidenceKind,
  safeParseVoucherRows,
  calcF3BookAmounts,
  type F3VoucherCheckRow,
} from '../useF3VoucherCheck'

function rowWith(patch: Partial<F3VoucherCheckRow>): F3VoucherCheckRow {
  return { ...emptyVoucherRow(1), ...patch }
}

describe('sectionEvidenceKind', () => {
  it('借方与日后区为付款证据，贷方区为采购证据', () => {
    expect(sectionEvidenceKind('debit')).toBe('payment')
    expect(sectionEvidenceKind('subsequent')).toBe('payment')
    expect(sectionEvidenceKind('credit')).toBe('purchase')
  })
})

describe('evaluateF3VoucherEvidence — payment（付款审批单+银行回单）', () => {
  it('单据齐全且金额一致 → 全部 ok', () => {
    const row = rowWith({
      voucherNo: 'PZ-001', amount: 100000,
      approvalDateNo: '2025-03-01/SP-01', approvalProper: '是',
      bankReceiptDate: '2025-03-02', bankPayee: '甲公司', bankAmount: 100000,
    })
    const checks = evaluateF3VoucherEvidence(row, 'payment')
    expect(checks).toHaveLength(3)
    expect(checks.every((c) => c.status === 'ok')).toBe(true)
  })

  it('回单金额与凭证金额不符 → 银行回单 mismatch', () => {
    const row = rowWith({
      voucherNo: 'PZ-001', amount: 100000,
      approvalDateNo: 'SP-01', bankReceiptDate: '2025-03-02', bankAmount: 99000,
    })
    const checks = evaluateF3VoucherEvidence(row, 'payment')
    expect(checks.find((c) => c.key === 'bank')?.status).toBe('mismatch')
  })

  it('审批不恰当 → 付款审批单 mismatch；未登记单据 → missing', () => {
    const row = rowWith({ voucherNo: 'PZ-001', amount: 50000, approvalDateNo: 'SP-02', approvalProper: '否' })
    const checks = evaluateF3VoucherEvidence(row, 'payment')
    expect(checks.find((c) => c.key === 'approval')?.status).toBe('mismatch')
    expect(checks.find((c) => c.key === 'bank')?.status).toBe('missing')
  })
})

describe('evaluateF3VoucherEvidence — purchase（入库单+采购发票）', () => {
  it('发票金额一致 → ok；发票金额不符 → mismatch', () => {
    const ok = rowWith({
      voucherNo: 'PZ-101', amount: 200000,
      receiptDateNo: 'RK-01', receiptProduct: '钢材',
      invoiceDateNo: 'FP-01', invoiceCounterparty: '乙公司', invoiceAmount: 200000,
    })
    expect(evaluateF3VoucherEvidence(ok, 'purchase').every((c) => c.status === 'ok')).toBe(true)

    const bad = rowWith({ ...ok, invoiceAmount: 180000 })
    expect(evaluateF3VoucherEvidence(bad, 'purchase').find((c) => c.key === 'invoice')?.status).toBe('mismatch')
  })

  it('未登记入库单与发票 → 均 missing', () => {
    const row = rowWith({ voucherNo: 'PZ-102', amount: 30000 })
    const checks = evaluateF3VoucherEvidence(row, 'purchase')
    expect(checks.find((c) => c.key === 'receipt')?.status).toBe('missing')
    expect(checks.find((c) => c.key === 'invoice')?.status).toBe('missing')
  })
})

describe('isBlankVoucherRow / safeParseVoucherRows', () => {
  it('空行判定', () => {
    expect(isBlankVoucherRow(emptyVoucherRow(1))).toBe(true)
    expect(isBlankVoucherRow(rowWith({ voucherNo: 'X' }))).toBe(false)
    expect(isBlankVoucherRow(rowWith({ amount: 1 }))).toBe(false)
  })

  it('解析时修剪空行并重排序号', () => {
    const json = JSON.stringify([
      { voucherNo: 'A', amount: 100 },
      {},
      { voucherNo: 'B', amount: 200 },
    ])
    const rows = safeParseVoucherRows(json, 'debit')
    expect(rows).toHaveLength(2)
    expect(rows.map((r) => r.seq)).toEqual([1, 2])
    expect(rows.map((r) => r.voucherNo)).toEqual(['A', 'B'])
  })

  it('非法JSON返回空数组', () => {
    expect(safeParseVoucherRows('not-json', 'debit')).toEqual([])
    expect(safeParseVoucherRows(null, 'credit')).toEqual([])
  })
})

describe('旧数据迁移', () => {
  it('summary → businessContent；旧核对列合并进 issueDesc；auditConclusion 推导 isAbnormal', () => {
    const legacy = JSON.stringify([{
      rowId: 'old-1', seq: 1, summary: '开票采购', counterAccount: '应付账款',
      amount: 88000, voucherDate: '2025-05-01', voucherNo: 'PZ-88',
      noteType: '银行承兑汇票', acceptor: '某银行',
      purchaseContractCheck: '相符', goodsReceiptCheck: '已验收',
      auditConclusion: '金额与合同不符', remark: '需追加程序',
    }])
    const rows = safeParseVoucherRows(legacy, 'credit')
    expect(rows).toHaveLength(1)
    const row = rows[0]
    expect(row.rowId).toBe('old-1')
    expect(row.businessContent).toBe('开票采购')
    expect(row.amount).toBe(88000)
    expect(row.noteType).toBe('银行承兑汇票')
    // 贷方区旧 acceptor → 对手方名称
    expect(row.invoiceCounterparty).toBe('某银行')
    expect(row.isAbnormal).toBe('是')
    expect(row.issueDesc).toContain('采购合同核对：相符')
    expect(row.issueDesc).toContain('金额与合同不符')
    expect(row.issueDesc).toContain('需追加程序')
  })

  it('借方区旧 acceptor → 收款方；无异常结论 → isAbnormal 否', () => {
    const legacy = JSON.stringify([{
      summary: '到期兑付', amount: 50000, voucherNo: 'PZ-9',
      acceptor: '开户银行', auditConclusion: '无异常',
    }])
    const rows = safeParseVoucherRows(legacy, 'debit')
    expect(rows[0].bankPayee).toBe('开户银行')
    expect(rows[0].isAbnormal).toBe('否')
    expect(rows[0].issueDesc).toBe('')
  })

  it('新结构字段原样保留', () => {
    const fresh = JSON.stringify([{
      voucherNo: 'PZ-1', businessContent: '兑付', amount: 10000,
      approvalDateNo: 'SP-1', approvalProper: '是',
      bankReceiptDate: '2025-06-01', bankPayee: '丙公司', bankAmount: 10000,
      indexNo: 'F3-7-1', isAbnormal: '否', issueDesc: '核对无误',
    }])
    const rows = safeParseVoucherRows(fresh, 'debit')
    expect(rows[0].approvalDateNo).toBe('SP-1')
    expect(rows[0].bankAmount).toBe(10000)
    expect(rows[0].issueDesc).toBe('核对无误')
  })
})

describe('calcF3BookAmounts — 检查比例账面数（来自F3-2）', () => {
  it('借方=本期承兑合计、贷方=本期开票合计、期末=审定数合计', () => {
    const detail = JSON.stringify([
      { currentAccepted: 100, currentIssued: 300, closingAdjusted: 500 },
      { currentAccepted: 50, currentIssued: 200, closingAdjusted: 250 },
    ])
    const book = calcF3BookAmounts(detail)
    expect(book.bookDebit).toBe(150)
    expect(book.bookCredit).toBe(500)
    expect(book.bookClosing).toBe(750)
  })

  it('兼容旧字段 increase/decrease/endBalance', () => {
    const detail = JSON.stringify([{ decrease: 80, increase: 120, endBalance: 40 }])
    const book = calcF3BookAmounts(detail)
    expect(book.bookDebit).toBe(80)
    expect(book.bookCredit).toBe(120)
    expect(book.bookClosing).toBe(40)
  })

  it('无 closingAdjusted 时按明细公式重算期末审定', () => {
    // 期初200 + 开票100 - 承兑50 = 250
    const detail = JSON.stringify([{
      openingBalance: 200,
      currentIssued: 100,
      currentAccepted: 50,
      aje: 0,
      rje: 0,
    }])
    const book = calcF3BookAmounts(detail)
    expect(book.bookDebit).toBe(50)
    expect(book.bookCredit).toBe(100)
    expect(book.bookClosing).toBe(250)
  })
})
