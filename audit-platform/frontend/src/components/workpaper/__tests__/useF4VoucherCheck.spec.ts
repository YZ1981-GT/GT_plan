import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  calcF4BookAmounts,
  evaluateF4VoucherEvidence,
  migrateF4VoucherRows,
  useF4VoucherCheck,
} from '../composables/useF4VoucherCheck'
import type { ChecklistResponse } from '../composables/useF4FormData'

function options(entries: Array<[string, unknown]> = []) {
  const allResponses = ref(new Map<string, ChecklistResponse>(
    entries.map(([key, value]) => [key, {
      item_id: key,
      conclusion: null,
      remark: typeof value === 'string' ? value : JSON.stringify(value),
    }]),
  ))
  return {
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses,
    isReadonly: ref(false),
  }
}

describe('F4-8 证据勾稽', () => {
  it('借方：回单金额与凭证不符、收款方不一致 → mismatch', () => {
    const checks = evaluateF4VoucherEvidence({
      rowId: 'r1', seq: 1, attSlot: 1,
      supplierName: '甲公司', voucherDate: '2025-06-01', voucherNo: '记-1',
      businessContent: '付货款', counterAccount: '1002', detailAccount: '',
      amount: 1000,
      approvalDateNo: 'SP-01', approvalProper: '是',
      bankReceiptDate: '2025-06-02', bankPayee: '乙公司', bankAmount: 900,
      receiptDateNo: '', receiptProduct: '', receiptUnit: '', receiptQty: 0,
      invoiceDateNo: '', invoiceCounterparty: '', invoiceAmount: 0,
      otherEvidence: '', indexNo: '', isAbnormal: '', issueDesc: '', sampleSource: '',
    }, 'payment')
    expect(checks.find((c) => c.key === 'bank')?.status).toBe('mismatch')
  })

  it('贷方：发票金额勾稽一致 → ok', () => {
    const checks = evaluateF4VoucherEvidence({
      rowId: 'r2', seq: 1, attSlot: 1,
      supplierName: '丙公司', voucherDate: '2025-07-01', voucherNo: '记-2',
      businessContent: '采购', counterAccount: '1405', detailAccount: '',
      amount: 2000,
      approvalDateNo: '', approvalProper: '',
      bankReceiptDate: '', bankPayee: '', bankAmount: 0,
      receiptDateNo: 'RK-1', receiptProduct: '钢材', receiptUnit: '吨', receiptQty: 2,
      invoiceDateNo: 'FP-1', invoiceCounterparty: '丙公司', invoiceAmount: 2000,
      otherEvidence: '', indexNo: 'F4-8-1', isAbnormal: '否', issueDesc: '', sampleSource: '',
    }, 'purchase')
    expect(checks.every((c) => c.status === 'ok')).toBe(true)
  })
})

describe('F4-8 旧数据迁移', () => {
  it('旧三单匹配字段迁移到源表证据字段并保留异常说明', () => {
    const row = migrateF4VoucherRows(JSON.stringify([{
      id: 'old-d',
      counterparty: '丁公司',
      voucherDate: '2025-01-01',
      voucherNo: '记-9',
      summary: '付款',
      amount: 500,
      paymentApproval: 'SP-9',
      bankReconciliation: '流水已核',
      threeWayMatch: '不一致',
      auditConclusion: '需补充回单',
    }]), 'debit')[0]
    expect(row).toMatchObject({
      rowId: 'old-d',
      supplierName: '丁公司',
      voucherNo: '记-9',
      businessContent: '付款',
      amount: 500,
      approvalDateNo: 'SP-9',
      isAbnormal: '是',
    })
    expect(row.issueDesc).toContain('原三单匹配')
    expect(row.issueDesc).toContain('需补充回单')
  })
})

describe('F4-8 检查比例与抽凭分配', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('账面金额取自F4-2借贷发生合计', () => {
    const book = calcF4BookAmounts(JSON.stringify([
      { currentDebit: 100, currentCredit: 200 },
      { currentDebit: 50, currentCredit: 80 },
    ]))
    expect(book).toEqual({ bookDebit: 150, bookCredit: 280 })
  })

  it('抽凭样本按借贷方向分配，并计算检查比例', () => {
    const opts = options([
      ['F4-2-rows', [
        { currentDebit: 1000, currentCredit: 5000 },
        { currentDebit: 1000, currentCredit: 5000 },
      ]],
    ])
    const api = useF4VoucherCheck(opts)
    api.applySamplingResults([
      {
        voucherDate: '2025-03-01',
        voucherNo: '记-D1',
        summary: '付款',
        counterpartAccount: '1002',
        debitAmount: '800',
        creditAmount: '',
      } as any,
      {
        voucherDate: '2025-03-02',
        voucherNo: '记-C1',
        summary: '采购',
        counterpartAccount: '1405',
        debitAmount: '',
        creditAmount: '4000',
      } as any,
    ], 'replace')

    expect(api.debitRows.value).toHaveLength(1)
    expect(api.creditRows.value).toHaveLength(1)
    expect(api.debitTotal.value).toBe(800)
    expect(api.creditTotal.value).toBe(4000)
    expect(api.checkRatios.value[0]).toMatchObject({
      label: '本期借方',
      bookAmount: 2000,
      checkedAmount: 800,
      ratio: 40,
    })
    expect(api.checkRatios.value[1]).toMatchObject({
      label: '本期贷方',
      bookAmount: 10000,
      checkedAmount: 4000,
      ratio: 40,
    })

    vi.advanceTimersByTime(1300)
  })

  it('弹窗保存回填更新借方证据字段', () => {
    const opts = options([
      ['F4-8-debit-rows', [{
        rowId: 'r1',
        supplierName: '甲公司',
        voucherNo: '记-1',
        amount: 1000,
      }]],
    ])
    const api = useF4VoucherCheck(opts)
    const row = api.debitRows.value[0]
    api.saveRow('debit', {
      ...row,
      approvalDateNo: 'SP-1',
      approvalProper: '是',
      bankReceiptDate: '2025-06-02',
      bankPayee: '甲公司',
      bankAmount: 1000,
      isAbnormal: '否',
    })
    expect(api.debitRows.value[0]).toMatchObject({
      approvalDateNo: 'SP-1',
      bankAmount: 1000,
      isAbnormal: '否',
    })
    const checks = evaluateF4VoucherEvidence(api.debitRows.value[0], 'payment')
    expect(checks.every((c) => c.status === 'ok')).toBe(true)
  })
})
