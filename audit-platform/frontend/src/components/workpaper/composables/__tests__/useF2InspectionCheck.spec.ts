import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF2PurchaseInboundCheck, useF2MaterialUsageCheck } from '../useF2InspectionCheck'
import { assessPurchaseAbnormal, assessMaterialAbnormal, calcSubClosing } from '../useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../useF2ValuationFormData'
import type { SampledVoucher } from '../useSamplingAlgorithms'

function makeVoucher(overrides: Partial<SampledVoucher> = {}): SampledVoucher {
  return {
    voucherNo: '记-001',
    voucherDate: '2025-06-15',
    summary: '原材料采购',
    debitAmount: '10000',
    creditAmount: null,
    accountCode: '1401',
    accountName: '原材料',
    counterpartAccount: '供应商A',
    voucherType: '记',
    accountingPeriod: 6,
    checkResult: 'unchecked',
    abnormal: false,
    remark: '',
    selected: true,
    phase: 'final',
    editTrail: [],
    ...overrides,
  }
}

describe('useF2InspectionCheck fillFromSampling', () => {
  it('F2-33 maps debit amount from voucher', () => {
    const map = ref<Map<string, ChecklistResponse>>(new Map())
    const ic = useF2PurchaseInboundCheck({
      allResponses: map,
      isReadonly: ref(false),
    })
    ic.fillFromSampling([makeVoucher()], 'replace')
    expect(ic.rows.value[0].amount).toBe(10000)
    expect(ic.rows.value[0].voucherNo).toBe('记-001')
    expect(ic.rows.value[0].sampleSource).toContain('抽凭引擎')
  })

  it('F2-34 maps credit amount from voucher', () => {
    const map = ref<Map<string, ChecklistResponse>>(new Map())
    const ic = useF2MaterialUsageCheck({
      allResponses: map,
      isReadonly: ref(false),
    })
    ic.fillFromSampling([makeVoucher({ debitAmount: null, creditAmount: '5000' })], 'replace')
    expect(ic.rows.value[0].amount).toBe(5000)
  })

  it('merge mode deduplicates by voucherNo', () => {
    const map = ref<Map<string, ChecklistResponse>>(new Map())
    const ic = useF2PurchaseInboundCheck({
      allResponses: map,
      isReadonly: ref(false),
    })
    ic.fillFromSampling([makeVoucher()], 'replace')
    ic.fillFromSampling([makeVoucher(), makeVoucher({ voucherNo: '记-002' })], 'merge')
    expect(ic.rows.value.length).toBe(2)
  })
})

describe('inspection abnormal assess', () => {
  it('flags qty mismatch on purchase', () => {
    expect(assessPurchaseAbnormal({
      id: '1', seq: 1, party: '', invCategory: '', voucherNo: 'V1', businessContent: '',
      itemName: '', unit: '', qty: 10, amount: 100, counterpartAccount: '', counterpartDetail: '',
      recvDateNo: 'RK1', recvQty: 8, inspectDateNo: '', logisticsDateNo: '', logisticsProvider: '',
      invoiceQty: 0, invoiceDateNo: '', invoiceParty: '', invoiceAmount: 0, indexRef: '',
      isAbnormal: false, abnormalOverride: null, remark: '',
    })).toBe(true)
  })

  it('flags missing doc on material usage', () => {
    expect(assessMaterialAbnormal({
      id: '1', seq: 1, party: '', voucherNo: 'V1', businessContent: '', itemName: '',
      unit: '', qty: 5, amount: 50, counterpartAccount: '', counterpartDetail: '',
      docDateNo: '', docQty: 0, indexRef: '', isAbnormal: false, abnormalOverride: null, remark: '',
    })).toBe(true)
  })

  it('subcontract closing formula', () => {
    expect(calcSubClosing({ opening: 100, increase: 40, decrease: 30 })).toBe(110)
  })
})
