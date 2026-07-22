/**
 * i2RecoverableModel 单元测试 — 对齐 Excel I2-16 公式
 * 样例：销售协议 1000 − 处置费用 60 = 公允净额 940；DCF < 公允 → 可收回 = 940
 */
import { describe, it, expect } from 'vitest'
import {
  calcI2RecoverableResult,
  defaultFvDisposal,
  defaultWaccParams,
  validateWaccParams,
  buildI2ConclusionDraft,
  buildI216SyncChecks,
  classifyI216SyncStatus,
  applyPreferValueInUse,
  compareI2Wacc,
  buildI2SensitivityNote,
} from '../i2RecoverableModel'

describe('i2RecoverableModel', () => {
  it('公允净额：优先销售协议，减处置费用合计（对齐 Excel 第一节）', () => {
    const fv = defaultFvDisposal()
    fv.salesAgreementPrice = 1000
    fv.activeMarketPrice = 990
    fv.estimatedPrice = 990
    fv.legalFees = 10
    fv.relatedTaxes = 20
    fv.transportCosts = 10
    fv.directCosts = 10
    fv.otherCosts = 10

    const result = calcI2RecoverableResult({
      cashFlows: [0, 0, 0, 0, 0],
      manualDiscountRate: 0.08,
      growthRate: 0,
      fvDisposal: fv,
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
    })

    expect(result.fairValueSource).toBe('销售协议价格')
    expect(result.disposalTotal).toBe(60)
    expect(result.fairValueLessDisposal).toBe(940)
  })

  it('可收回金额 = MAX(公允净额, DCF)，对应 N23=MAX(N14,N20)', () => {
    const fv = defaultFvDisposal()
    fv.salesAgreementPrice = 1000
    fv.legalFees = 60

    const result = calcI2RecoverableResult({
      cashFlows: [200, 200, 200, 200, 200],
      manualDiscountRate: 0.08,
      growthRate: 0,
      fvDisposal: fv,
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
    })

    expect(result.fairValueLessDisposal).toBe(940)
    expect(result.valueInUse).toBeGreaterThan(0)
    expect(result.recoverableAmount).toBe(
      Math.max(result.fairValueLessDisposal, result.valueInUse),
    )
    expect(result.recoverableSource).toBe(
      result.fairValueLessDisposal >= result.valueInUse ? '公允净额' : '使用价值(DCF)',
    )
  })

  it('WACC 就绪时使用税前折现率（CAS8 默认）', () => {
    const wacc = defaultWaccParams()
    wacc.taxRate = 25
    wacc.totalDebt = 500
    wacc.totalEquity = 500
    wacc.costOfDebt = 10
    wacc.riskFreeRate = 4
    wacc.beta = 1.1
    wacc.marketReturn = 10

    const result = calcI2RecoverableResult({
      cashFlows: [200, 200, 200, 200, 200],
      manualDiscountRate: 0.08,
      growthRate: 0,
      fvDisposal: defaultFvDisposal(),
      waccParams: wacc,
      usePreTaxRate: true,
    })

    expect(result.waccAfterTax).toBeGreaterThan(0)
    expect(result.preTaxDiscountRate).toBeGreaterThan(result.waccAfterTax)
    expect(result.effectiveDiscountRate).toBeCloseTo(result.preTaxDiscountRate / 100, 6)
  })

  it('旧数据兼容：无公允明细时使用 legacyFairValueNet', () => {
    const result = calcI2RecoverableResult({
      cashFlows: [100, 100, 100, 100, 100],
      manualDiscountRate: 0.1,
      growthRate: 0,
      fvDisposal: defaultFvDisposal(),
      waccParams: defaultWaccParams(),
      usePreTaxRate: true,
      legacyFairValueNet: 500,
    })
    expect(result.fairValueLessDisposal).toBe(500)
    expect(result.fairValueSource).toBe('手工净额')
    expect(result.recoverableAmount).toBe(Math.max(500, result.valueInUse))
  })

  it('校验：Rm=1.10 触发百分比口径警告（源表示例常见错误）', () => {
    const wacc = defaultWaccParams()
    wacc.taxRate = 25
    wacc.totalDebt = 500
    wacc.totalEquity = 500
    wacc.costOfDebt = 10
    wacc.riskFreeRate = 4
    wacc.beta = 1.1
    wacc.marketReturn = 1.1

    const msgs = validateWaccParams(wacc)
    expect(msgs.some((m) => m.includes('Rm') && (m.includes('过小') || m.includes('偏低')))).toBe(true)
  })

  it('结论草稿包含可收回来源与减值提示', () => {
    const text = buildI2ConclusionDraft({
      assetName: '项目A',
      fairValueNet: 940,
      valueInUse: 180.94,
      recoverableAmount: 940,
      recoverableSource: '公允净额',
      bookValue: 800,
      effectiveDiscountRate: 0.08,
      growthRate: 0,
      fromWacc: false,
    })
    expect(text).toContain('项目A')
    expect(text).toContain('940.00')
    expect(text).toContain('公允净额')
    expect(text).toContain('无需计提减值')
  })

  it('I2-15↔I2-16 一致性分类（③④⑤）', () => {
    expect(
      classifyI216SyncStatus(
        { needTest: true, linkedToDcf: true, fairValueLessDisposal: 0, dcfValue: 0, recoverableAmount: 0 },
        null,
      ).status,
    ).toBe('missing-i16')

    expect(
      classifyI216SyncStatus(
        { needTest: true, linkedToDcf: true, fairValueLessDisposal: 100, dcfValue: 80, recoverableAmount: 100 },
        { fairValueLessDisposal: 100, valueInUse: 80, recoverableAmount: 100 },
      ).status,
    ).toBe('synced')

    expect(
      classifyI216SyncStatus(
        { needTest: true, linkedToDcf: true, fairValueLessDisposal: 100, dcfValue: 80, recoverableAmount: 100 },
        { fairValueLessDisposal: 200, valueInUse: 80, recoverableAmount: 200 },
      ).status,
    ).toBe('stale')

    expect(
      classifyI216SyncStatus(
        { needTest: false, linkedToDcf: false, fairValueLessDisposal: 0, dcfValue: 0, recoverableAmount: 0 },
        null,
      ).status,
    ).toBe('no-test')

    const checks = buildI216SyncChecks(
      [{ name: 'A', needTest: true, linkedToDcf: true, fairValueLessDisposal: 100, dcfValue: 80, recoverableAmount: 100 }],
      [{ name: 'A', fairValueLessDisposal: 100, valueInUse: 80, recoverableAmount: 100 }],
    )
    expect(checks[0].status).toBe('synced')
  })

  it('仅使用价值：可收回取 DCF 且要求理由', () => {
    const r = applyPreferValueInUse(940, 180, true, '')
    expect(r.recoverableAmount).toBe(180)
    expect(r.recoverableSource).toContain('使用价值')
    expect(r.warnings.length).toBeGreaterThan(0)

    const r2 = applyPreferValueInUse(940, 180, true, '无活跃市场')
    expect(r2.warnings).toHaveLength(0)
  })

  it('WACC 对比：百分数与小数口径可混用', () => {
    const c = compareI2Wacc({ currentWacc: 10, priorWacc: 0.08, industryWacc: 0.09 })
    expect(c.vsPriorBp).toBe(200)
    expect(c.warnings.length).toBeGreaterThan(0)
  })

  it('敏感性说明可生成', () => {
    const note = buildI2SensitivityNote({
      assetName: '项目A',
      scenarios: [
        { scenario: '基准', recoverableAmount: 100, differenceFromBase: 0 },
        { scenario: '折现率 +1%', recoverableAmount: 90, differenceFromBase: -10 },
      ],
    })
    expect(note).toContain('敏感性分析')
    expect(note).toContain('项目A')
  })
})
