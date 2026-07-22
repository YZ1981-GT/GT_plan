/**
 * i1RecoverableModel 单元测试 — 对齐 Excel I1-13 公式
 */
import { describe, it, expect } from 'vitest'
import {
  resolveI1FairValue,
  calcI1DisposalTotal,
  calcFairValueNet,
  calcEffectiveDiscountRate,
  calcI1RecoverableResult,
  defaultFvDisposal,
  defaultWaccParams,
  buildI1ConclusionDraft,
  validateWaccParams,
  buildI113SyncChecks,
} from '../i1RecoverableModel'

describe('i1RecoverableModel', () => {
  it('公允取值优先级：销售协议 > 活跃市场 > 估计（Excel N=IF）', () => {
    const fv = {
      ...defaultFvDisposal(),
      salesAgreementPrice: 1000,
      activeMarketPrice: 990,
      estimatedPrice: 980,
    }
    expect(resolveI1FairValue(fv)).toEqual({ value: 1000, source: '销售协议价格' })

    fv.salesAgreementPrice = 0
    expect(resolveI1FairValue(fv)).toEqual({ value: 990, source: '活跃市场价格' })

    fv.activeMarketPrice = 0
    expect(resolveI1FairValue(fv)).toEqual({ value: 980, source: '估计价格' })
  })

  it('处置费用合计与公允净额', () => {
    const fv = {
      ...defaultFvDisposal(),
      salesAgreementPrice: 1000,
      legalFees: 10,
      relatedTaxes: 20,
      transportCosts: 10,
      directCosts: 10,
      otherCosts: 10,
    }
    expect(calcI1DisposalTotal(fv)).toBe(60)
    expect(calcFairValueNet(fv)).toBe(940)
  })

  it('WACC：Ke / 税后 / 税前（百分比口径）', () => {
    const wacc = {
      taxRate: 25,
      totalDebt: 500,
      totalEquity: 1000,
      costOfDebt: 10,
      riskFreeRate: 4,
      beta: 1.1,
      marketReturn: 10, // 正确：10% 而非 110%
    }
    const r = calcEffectiveDiscountRate(wacc, 0.08, true)
    // Ke = 4 + 1.1*(10-4) = 10.6
    expect(r.costOfEquity).toBeCloseTo(10.6, 5)
    // WACC税后 = 1000/1500*10.6 + 500/1500*10*(1-0.25) = 7.066... + 2.5 = 9.566...
    expect(r.waccAfterTax).toBeCloseTo(9.5667, 2)
    // 税前 = 税后/(1-0.25)
    expect(r.preTaxDiscountRate).toBeCloseTo(r.waccAfterTax / 0.75, 5)
    expect(r.fromWacc).toBe(true)
    expect(r.effectiveRate).toBeCloseTo(r.preTaxDiscountRate / 100, 5)
  })

  it('WACC 未就绪时回退手工折现率', () => {
    const r = calcEffectiveDiscountRate(defaultWaccParams(), 0.08, true)
    expect(r.fromWacc).toBe(false)
    expect(r.effectiveRate).toBeCloseTo(0.08, 5)
  })

  it('可收回金额 = MAX(公允净额, DCF)，对应 N23=MAX(N14,N20)', () => {
    const fv = {
      ...defaultFvDisposal(),
      salesAgreementPrice: 1000,
      legalFees: 60,
    }
    const result = calcI1RecoverableResult({
      cashFlows: [200, 200, 200, 200, 200],
      manualDiscountRate: 0.1,
      growthRate: 0.02,
      fvDisposal: fv,
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
    })
    expect(result.fairValueLessDisposal).toBe(940)
    expect(result.valueInUse).toBeGreaterThan(0)
    expect(result.recoverableAmount).toBe(Math.max(result.fairValueLessDisposal, result.valueInUse))
    expect(result.recoverableSource).toBe(
      result.fairValueLessDisposal >= result.valueInUse ? '公允净额' : '使用价值(DCF)',
    )
    expect(result.discountFactors).toHaveLength(5)
    expect(result.discountFactors[0]).toBeCloseTo(1 / 1.1, 5)
  })

  it('r≤g 时终值无效', () => {
    const result = calcI1RecoverableResult({
      cashFlows: [100, 100, 100, 100, 100],
      manualDiscountRate: 0.02,
      growthRate: 0.03,
      fvDisposal: defaultFvDisposal(),
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
      legacyFairValueNet: 50,
    })
    expect(result.rateInvalid).toBe(true)
    expect(result.terminalValue).toBe(0)
    expect(result.discountedTerminalValue).toBe(0)
  })

  it('旧数据兼容：无公允明细时使用 legacyFairValueNet', () => {
    const result = calcI1RecoverableResult({
      cashFlows: [0, 0, 0, 0, 0],
      manualDiscountRate: 0.08,
      growthRate: 0,
      fvDisposal: defaultFvDisposal(),
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
      legacyFairValueNet: 500,
    })
    expect(result.fairValueLessDisposal).toBe(500)
    expect(result.fairValueSource).toBe('手工净额')
    expect(result.recoverableAmount).toBe(500)
  })

  it('结论草稿包含关键结论要素', () => {
    const text = buildI1ConclusionDraft({
      assetName: '软件A',
      fairValueNet: 940,
      valueInUse: 180,
      recoverableAmount: 940,
      recoverableSource: '公允净额',
      bookValue: 800,
      effectiveDiscountRate: 0.1,
      growthRate: 0.02,
      fromWacc: false,
    })
    expect(text).toContain('软件A')
    expect(text).toContain('940.00')
    expect(text).toContain('无需计提减值')
  })
})

describe('validateWaccParams', () => {
  it('检测 Rm 填成小数或异常偏高', () => {
    expect(validateWaccParams({
      ...defaultWaccParams(),
      totalDebt: 100,
      totalEquity: 200,
      marketReturn: 0.08,
      riskFreeRate: 2.5,
    }).some((m) => m.includes('小数'))).toBe(true)

    expect(validateWaccParams({
      ...defaultWaccParams(),
      totalDebt: 100,
      totalEquity: 200,
      marketReturn: 110,
      riskFreeRate: 4,
    }).some((m) => m.includes('偏高'))).toBe(true)
  })

  it('正常百分比不报警', () => {
    expect(validateWaccParams({
      taxRate: 25,
      totalDebt: 500,
      totalEquity: 1000,
      costOfDebt: 5,
      riskFreeRate: 2.5,
      beta: 1.1,
      marketReturn: 8,
    })).toEqual([])
  })
})

describe('buildI113SyncChecks', () => {
  it('须测试缺 I1-13 → missing-i13', () => {
    const checks = buildI113SyncChecks(
      [{ name: 'A', needTest: true, fairValueLessDisposal: 0, dcfValue: 0, recoverableAmount: 0 }],
      [],
    )
    expect(checks[0].status).toBe('missing-i13')
  })

  it('同名数值一致 → synced', () => {
    const checks = buildI113SyncChecks(
      [{ name: 'A', needTest: true, fairValueLessDisposal: 100, dcfValue: 80, recoverableAmount: 100 }],
      [{ name: 'A', fairValueLessDisposal: 100, valueInUse: 80, recoverableAmount: 100 }],
    )
    expect(checks[0].status).toBe('synced')
  })

  it('数值漂移 → stale', () => {
    const checks = buildI113SyncChecks(
      [{ name: 'A', needTest: true, fairValueLessDisposal: 100, dcfValue: 80, recoverableAmount: 100 }],
      [{ name: 'A', fairValueLessDisposal: 200, valueInUse: 80, recoverableAmount: 200 }],
    )
    expect(checks[0].status).toBe('stale')
    expect(checks[0].message).toContain('不一致')
  })

  it('无须测试 → no-test', () => {
    const checks = buildI113SyncChecks(
      [{ name: 'B', needTest: false, fairValueLessDisposal: 0, dcfValue: 0, recoverableAmount: 0 }],
      [],
    )
    expect(checks[0].status).toBe('no-test')
  })
})
