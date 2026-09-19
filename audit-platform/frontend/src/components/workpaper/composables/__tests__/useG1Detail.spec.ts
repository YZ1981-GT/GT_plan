import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  enrichDetailRow,
  useG1Detail,
  type TradingDetailRow,
} from '../useG1Detail'
import type { ChecklistResponse } from '../useF1FormData'

function baseRow(partial: Partial<TradingDetailRow> = {}): TradingDetailRow {
  return enrichDetailRow({
    id: '1',
    seq: 1,
    securityName: '测试债',
    securityCode: 'B001',
    acctClass: 'trading',
    investType: 'bond',
    market: '',
    acquisitionDate: '',
    initialCost: 100,
    originalCurrency: '',
    exchangeRate: 0,
    openingQuantity: 0,
    boughtQuantity: 0,
    soldQuantity: 0,
    closingQuantity: 0,
    openingCost: 100,
    openingCumulativeFv: 10,
    openingFairValue: 0,
    openingCostAdj: 0,
    openingFvAdj: 0,
    auditedOpeningCost: 0,
    auditedOpeningCumulativeFv: 0,
    auditedOpeningFvTotal: 0,
    openingLtDeduction: 0,
    openingReported: 0,
    addedCost: 20,
    reducedCost: 5,
    periodFvChange: 3,
    dividendIncome: 2,
    unitFairValue: 0,
    closingFairValue: 0,
    fairValueSource: '1',
    fairValueChange: 0,
    cumulativeFVChange: 0,
    quoteDate: '',
    closingCost: 0,
    closingCostAdj: 0,
    closingFvAdj: 0,
    auditedClosingCost: 0,
    auditedClosingCumulativeFv: 0,
    auditedClosingFvTotal: 0,
    closingLtDeduction: 0,
    closingReported: 0,
    disposalProceeds: 0,
    disposalCost: 0,
    realizedGain: 0,
    totalIncome: 0,
    fvChangeInPL: 0,
    remark: '',
    unadjusted: 0,
    aje: 0,
    rje: 0,
    adjusted: 0,
    variance: 0,
    rollForwardDiff: 0,
    indexRef: '',
    realizationRestricted: false,
    pledged: false,
    ...partial,
  })
}

describe('enrichDetailRow 双桶滚动', () => {
  it('期初公允价值 = 成本 + 累计公允变动', () => {
    const r = baseRow({ openingCost: 100, openingCumulativeFv: 10 })
    expect(r.openingFairValue).toBe(110)
    expect(r.auditedOpeningFvTotal).toBe(110)
  })

  it('期末成本由期初审定滚动', () => {
    const r = baseRow({
      openingCost: 100,
      openingCostAdj: 5,
      addedCost: 20,
      reducedCost: 5,
      periodFvChange: 3,
      openingCumulativeFv: 10,
    })
    // 审定成本 105 +20 -5 = 120
    expect(r.auditedOpeningCost).toBe(105)
    expect(r.closingCost).toBe(120)
    expect(r.cumulativeFVChange).toBe(13) // 10 + 3
    expect(r.closingFairValue).toBe(133) // 120 + 13
  })

  it('一年以上扣减得到报表数', () => {
    const r = baseRow({
      openingCost: 100,
      openingCumulativeFv: 0,
      periodFvChange: 0,
      addedCost: 0,
      reducedCost: 0,
      closingLtDeduction: 40,
    })
    expect(r.auditedClosingFvTotal).toBe(100)
    expect(r.closingReported).toBe(60)
  })

  it('AJE/RJE 计入期末审定公允价值', () => {
    const r = baseRow({
      openingCost: 100,
      openingCumulativeFv: 0,
      addedCost: 0,
      reducedCost: 0,
      periodFvChange: 0,
      aje: 7,
      rje: 3,
    })
    expect(r.auditedClosingFvTotal).toBe(110)
    expect(r.adjusted).toBe(110)
  })

  it('旧数据仅有 openingFairValue 时可反推累计 FV', () => {
    const r = baseRow({
      openingCost: 80,
      openingCumulativeFv: 0,
      openingFairValue: 100,
      addedCost: 0,
      reducedCost: 0,
      periodFvChange: 0,
    })
    expect(r.openingCumulativeFv).toBe(20)
    expect(r.openingFairValue).toBe(100)
  })
})

describe('useG1Detail', () => {
  it('按会计分类汇总期末审定', () => {
    const rows = [
      {
        id: '1',
        seq: 1,
        securityName: 'A',
        acctClass: 'trading',
        investType: 'bond',
        openingCost: 100,
        openingCumulativeFv: 0,
        addedCost: 0,
        reducedCost: 0,
        periodFvChange: 0,
      },
      {
        id: '2',
        seq: 2,
        securityName: 'B',
        acctClass: 'designated_fvpl',
        investType: 'stock',
        openingCost: 50,
        openingCumulativeFv: 10,
        addedCost: 0,
        reducedCost: 0,
        periodFvChange: 0,
      },
    ]
    const allResponses = ref(
      new Map<string, ChecklistResponse>([
        ['G1-2-rows', { conclusion: JSON.stringify(rows) } as ChecklistResponse],
      ]),
    )
    const detail = useG1Detail({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    expect(detail.subtotalsByAcct.value).toHaveLength(2)
    expect(detail.grandTotal.value.auditedClosingFvTotal).toBe(160)
    expect(detail.gatesReady.value).toBe(false)
  })

  it('编制闸门完成后 gatesReady 为 true', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const detail = useG1Detail({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    detail.updateGates({
      inclusionReviewed: true,
      fraudRiskAssessed: true,
      fraudRiskFlag: false,
    })
    expect(detail.gatesReady.value).toBe(true)
  })
})
