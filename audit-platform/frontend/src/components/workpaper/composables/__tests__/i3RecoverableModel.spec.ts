/**
 * i3RecoverableModel — 对齐致同 I3-7 Excel 样例与 CAS8 公式链
 */
import { describe, it, expect } from 'vitest'
import {
  calcI3RecoverableResult,
  defaultFvDisposal,
  defaultWaccParams,
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  migrateLegacyCashFlows,
  validateGrowthRate,
  buildI3ConclusionDraft,
} from '../i3RecoverableModel'

describe('i3RecoverableModel', () => {
  // 源表示例：t=15%, D=300, E=1100, Kd=7%, Rf=3.77%, β=1.02, Rm=16.11%
  // Ke≈16.36%, WACC税后≈14.13%, 税前≈16.62%
  it('CAPM / WACC 对齐 Excel 样例参数', () => {
    const ke = calcCostOfEquity(3.77, 1.02, 16.11)
    expect(ke).toBeCloseTo(16.36, 1)

    const waccAt = calcWaccAfterTax(300, 1100, ke, 7, 15)
    expect(waccAt).toBeCloseTo(14.13, 1)

    const preTax = calcPreTaxDiscountRate(waccAt, 15)
    expect(preTax).toBeCloseTo(16.62, 1)
  })

  it('可收回金额 = MAX(公允净额, DCF)，对应 N23=MAX(N11,N20)', () => {
    const fv = defaultFvDisposal()
    fv.salesAgreementPrice = 1000
    fv.legalFees = 50
    fv.relatedTaxes = 50

    const result = calcI3RecoverableResult({
      cashFlows: [100, 100, 100, 100, 100],
      manualDiscountRate: 0.1,
      growthRate: 0,
      fvDisposal: fv,
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
    })

    expect(result.fairValueLessDisposal).toBe(900)
    expect(result.disposalTotal).toBe(100)
    expect(result.recoverableAmount).toBe(Math.max(900, result.valueInUse))
  })

  it('公允取值优先：销售协议 > 活跃市场 > 估计', () => {
    const fv = defaultFvDisposal()
    fv.estimatedPrice = 100
    fv.activeMarketPrice = 200
    fv.salesAgreementPrice = 300
    const result = calcI3RecoverableResult({
      cashFlows: [0, 0, 0, 0, 0],
      manualDiscountRate: 0.1,
      growthRate: 0,
      fvDisposal: fv,
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
    })
    expect(result.fairValueSource).toBe('销售协议价格')
    expect(result.fairValueLessDisposal).toBe(300)
  })

  it('旧版收入/成本拆分可迁移为税前净现金流', () => {
    const migrated = migrateLegacyCashFlows({
      revenue: [1000, 1100],
      cost: [600, 650],
      tax: [50, 55],
      depreciation: [80, 80],
      capex: [100, 100],
      wcChange: [20, 10],
    })
    expect(migrated).toEqual([
      1000 - 600 - 50 + 80 - 100 - 20,
      1100 - 650 - 55 + 80 - 100 - 10,
    ])
  })

  it('永续增长率高于对照上限时给出警告', () => {
    const msgs = validateGrowthRate(0.05, {
      industryGrowthRate: 0.03,
      marketGrowthRate: 0.02,
      countryGrowthRate: 0.025,
      growthRateBasis: '管理层判断',
    })
    expect(msgs.some((m) => m.includes('高于'))).toBe(true)
  })

  it('结论模板含商誉不可转回提示', () => {
    const text = buildI3ConclusionDraft({
      cguName: 'CGU-A',
      fairValueNet: 100,
      valueInUse: 80,
      recoverableAmount: 100,
      recoverableSource: '公允净额',
      bookValue: 150,
      effectiveDiscountRate: 0.1,
      growthRate: 0.02,
      fromWacc: true,
    })
    expect(text).toContain('CGU-A')
    expect(text).toContain('不得转回')
  })
})
