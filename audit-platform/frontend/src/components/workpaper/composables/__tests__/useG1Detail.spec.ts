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
    // 🔴 Task 14：原 addedCost 20 / reducedCost 5 合并为模板的净额单列 M
    periodCostChange: 15,
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
    // 🔴 Task 14 新补的模板 AA 列
    confirmationRequested: false,
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

  // 🔴 spec `g-cycle-single-region-detail-lanes` Task 14（用户拍板「跟模板一致」）：
  //    以下三条的期望值按**模板公式**改写，不是放宽判据 —— 模板 `明细表G1-2` 逐格实测：
  //      `P12=C12+M12`（期末成本起点是**期初余额成本 C**，不是期初审定成本 H）
  //      `Q12=D12+N12`（期末累计 FV 起点是**期初余额累计 FV D**，不是审定值）
  //      `Y12=W12+X12` / `L12=J12+K12`（**加**不是减 —— K/X 列名「减：…」⇒ 存负数）
  //      `W12=U12+V12`（**不含** AJE/RJE —— 那两列不在模板 27 列内、不受管）
  it('期末成本按模板 P=C+M（净额单列，起点是期初余额成本）', () => {
    const r = baseRow({
      openingCost: 100,
      openingCostAdj: 5,
      periodCostChange: 15, // 原 addedCost 20 − reducedCost 5
      periodFvChange: 3,
      openingCumulativeFv: 10,
    })
    expect(r.auditedOpeningCost).toBe(105) // H=C+F 不变
    expect(r.closingCost).toBe(115) // P=C+M=100+15（改造前是 H+增−减=120）
    expect(r.cumulativeFVChange).toBe(13) // Q=D+N=10+3
    expect(r.closingFairValue).toBe(128) // R=P+Q=115+13
  })

  it('报表数按模板 Y=W+X（扣减列存负数）', () => {
    const r = baseRow({
      openingCost: 100,
      openingCumulativeFv: 0,
      periodFvChange: 0,
      periodCostChange: 0,
      closingLtDeduction: -40, // 模板列名「减：超过一年到期的部分」⇒ 负数
    })
    expect(r.auditedClosingFvTotal).toBe(100)
    expect(r.closingReported).toBe(60) // Y=W+X=100+(-40)
  })

  it('AJE/RJE 不进期末审定公允价值（模板 W=U+V 不含调整列）', () => {
    const r = baseRow({
      openingCost: 100,
      openingCumulativeFv: 0,
      periodCostChange: 0,
      periodFvChange: 0,
      aje: 7,
      rje: 3,
    })
    expect(r.auditedClosingFvTotal).toBe(100) // W=U+V，与 aje/rje 无关
    expect(r.adjusted).toBe(100)
  })

  it('旧数据仅有 openingFairValue 时可反推累计 FV', () => {
    const r = baseRow({
      openingCost: 80,
      openingCumulativeFv: 0,
      openingFairValue: 100,
      periodCostChange: 0,
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
