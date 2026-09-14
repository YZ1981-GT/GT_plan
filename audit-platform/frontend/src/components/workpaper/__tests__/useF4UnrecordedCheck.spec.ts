import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  computeF4UnrecordedRow,
  migrateF4UnrecordedRows,
  useF4UnrecordedCheck,
} from '../composables/useF4UnrecordedCheck'
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

describe('F4-7源表公式', () => {
  it('付款期：期末=期初+贷方-借方，平均天数=365×期末÷贷方，差异=期后付款-期末', () => {
    const stored = migrateF4UnrecordedRows(JSON.stringify([{
      supplierName: '甲公司',
      openingBalance: 100,
      currentDebit: 150,
      currentCredit: 200,
      postPaymentAmount: 180,
      withinAverageDays: '否',
    }]), 'payment-window')[0]
    const row = computeF4UnrecordedRow(stored, 'payment-window')
    expect(row.closingBalance).toBe(150)
    expect(row.averagePaymentDays).toBe(273.75)
    expect(row.difference).toBe(30)
    expect(row.riskFlags).toContain('期后付款超过期末余额')
    expect(row.riskFlags).toContain('不在平均付款天数内')
  })

  it('暂估入库：暂估金额=数量×合同不含税单价', () => {
    const stored = migrateF4UnrecordedRows(JSON.stringify([{
      receiptNo: 'RK-001',
      quantity: 10,
      contractUnitPrice: 80,
      voucherNo: '记-12',
      voucherAmount: 750,
      shouldAdjust: '是',
    }]), 'estimated-inbound')[0]
    const row = computeF4UnrecordedRow(stored, 'estimated-inbound')
    expect(row.estimatedAmount).toBe(800)
    expect(row.riskFlags).toContain('暂估与凭证金额不一致')
    expect(row.riskFlags).toContain('存在建议调整')
  })
})

describe('F4-7旧三段数据迁移', () => {
  it('旧期后入库行迁移到暂估入库字段', () => {
    const row = migrateF4UnrecordedRows(JSON.stringify([{
      id: 'old-r',
      date: '2026-01-03',
      documentNo: 'RK-09',
      amount: 900,
      shouldRecordCurrent: '是',
      suggestion: '补提暂估',
    }]), 'estimated-inbound')[0]
    expect(row).toMatchObject({
      rowId: 'old-r',
      receiptDate: '2026-01-03',
      receiptNo: 'RK-09',
      estimatedAmount: 900,
      shouldAdjust: '是',
    })
    expect(row.remark).toContain('原入账建议：补提暂估')
  })

  it('旧期后收票行迁移到未处理发票字段', () => {
    const row = migrateF4UnrecordedRows(JSON.stringify([{
      date: '2026-01-10',
      counterparty: '乙公司',
      documentNo: 'FP-01',
      description: '设备维修',
      amount: 1200,
      shouldRecordCurrent: '是',
    }]), 'unprocessed-invoice')[0]
    expect(row).toMatchObject({
      invoiceDate: '2026-01-10',
      invoiceNo: 'FP-01',
      invoiceContent: '设备维修',
      supplierName: '乙公司',
      amount: 1200,
      reportPeriodAmount: 1200,
    })
  })
})

describe('useF4UnrecordedCheck — 五段汇总、OCR和截止提取', () => {
  it('汇总应计入报告期金额与建议调整', () => {
    const composable = useF4UnrecordedCheck(options([
      ['F4-7-estimated-inbound-rows', [{
        rowId: 'e1', receiptNo: 'RK1', quantity: 10, contractUnitPrice: 50,
        voucherAmount: 400, shouldAdjust: '是',
      }]],
      ['F4-7-unprocessed-invoice-rows', [{
        rowId: 'i1', invoiceNo: 'FP1', supplierName: '丙公司', amount: 300,
        shouldIncludeReportPeriod: '是', reportPeriodAmount: 300,
      }]],
      ['F4-7-subsequent-payment-rows', [{
        rowId: 'p1', voucherNo: '记1', bankDocumentNo: '银1', supplierName: '丁公司',
        amount: 200, shouldIncludeReportPeriod: '否', reportPeriodAmount: 0,
      }]],
    ]))
    expect(composable.getSubtotal('estimated-inbound').adjustmentTotal).toBe(100)
    expect(composable.overallSummary.value.reportPeriodAmount).toBe(300)
    expect(composable.overallSummary.value.candidateAdjustment).toBe(400)
  })

  it('OCR预览确认默认仅回填空字段，允许显式覆盖后二次编辑', () => {
    const opts = options([['F4-7-subsequent-payment-rows', [{
      rowId: 'p1',
      attSlot: 9,
      voucherNo: '人工凭证号',
      amount: 500,
    }]]])
    const composable = useF4UnrecordedCheck(opts)
    composable.mergeOcrFields('subsequent-payment', 'p1', {
      voucherNo: 'OCR凭证号',
      bankDocumentNo: 'BANK-01',
      supplierName: '供应商A',
      amount: 600,
    })
    let row = composable.getRows('subsequent-payment')[0]
    expect(row.voucherNo).toBe('人工凭证号')
    expect(row.amount).toBe(500)
    expect(row.bankDocumentNo).toBe('BANK-01')
    expect(row.supplierName).toBe('供应商A')

    composable.mergeOcrFields('subsequent-payment', 'p1', { voucherNo: '复核后编号' }, true)
    composable.updateCell('subsequent-payment', 'p1', 'remark', '二次编辑完成')
    row = composable.getRows('subsequent-payment')[0]
    expect(row.voucherNo).toBe('复核后编号')
    expect(row.remark).toBe('二次编辑完成')
    expect(row.attSlot).toBe(9)
  })

  it('同一供应商同金额跨区域出现时提示去重，避免直接累计为最终调整', () => {
    const composable = useF4UnrecordedCheck(options([
      ['F4-7-unprocessed-invoice-rows', [{
        supplierName: '重复供应商', amount: 500,
        shouldIncludeReportPeriod: '是', reportPeriodAmount: 500,
      }]],
      ['F4-7-subsequent-increase-rows', [{
        supplierName: '重复供应商', amount: 500,
        shouldIncludeReportPeriod: '是', reportPeriodAmount: 500,
      }]],
    ]))
    expect(composable.overallSummary.value.candidateAdjustment).toBe(1000)
    expect(composable.overallSummary.value.duplicateRiskCount).toBe(1)
  })

  it('截止自动提取按借方/贷方分配到期后付款和期后增加额', () => {
    const composable = useF4UnrecordedCheck(options())
    const result = composable.distributeCutoffSamples([
      {
        voucherNo: '付-1', voucherDate: '2026-01-05', summary: '支付货款',
        debitAmount: '100', creditAmount: '0',
      },
      {
        voucherNo: '购-1', voucherDate: '2026-01-08', summary: '采购入账',
        debitAmount: '0', creditAmount: '250',
      },
    ])
    expect(result).toEqual({ payments: 1, increases: 1 })
    expect(composable.getRows('subsequent-payment')[0]).toMatchObject({
      voucherNo: '付-1',
      amount: 100,
    })
    expect(composable.getRows('subsequent-increase')[0]).toMatchObject({
      voucherNo: '购-1',
      amount: 250,
    })
  })
})
