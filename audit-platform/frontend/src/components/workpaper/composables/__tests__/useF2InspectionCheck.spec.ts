import { describe, it, expect } from 'vitest'
// 抽凭回填（原 fillFromSampling 整表替换 / 按凭证号去重）改经共享回填函数，见 f2InspectionFill.spec
// （spec voucher-identity-writeback-and-audit-phase 任务 11）
import { assessPurchaseAbnormal, assessMaterialAbnormal, calcSubClosing } from '../useF2InspectionCheckFormulas'

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
