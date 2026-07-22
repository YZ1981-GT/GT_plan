/**
 * H1-15 可收回金额 / WACC / 公允净额 / 终值敏感轴 测试
 */
import { describe, it, expect } from 'vitest'
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  calcTerminalSensitivityAxis,
  type FairValueDisposal,
} from '../useH1Impairment'
import { calcDcfPresentValue, calcTerminalValue } from '../useH1DepreciationEngine'

function baseFv(overrides: Partial<FairValueDisposal> = {}): FairValueDisposal {
  return {
    assetName: '产线A',
    salesAgreementPrice: 0,
    salesAgreementNote: '',
    activeMarketPrice: 0,
    activeMarketNote: '',
    estimatedPrice: 0,
    estimatedNote: '',
    legalFees: 0,
    relatedTaxes: 0,
    transportCosts: 0,
    directCosts: 0,
    otherCosts: 0,
    remark: '',
    auditNote: '',
    ...overrides,
  }
}

describe('H1-15 CAPM / WACC', () => {
  it('Ke = Rf + β×(Rm−Rf)', () => {
    expect(calcCostOfEquity(2.5, 1.2, 10)).toBeCloseTo(11.5, 6)
  })

  it('税后WACC = E/V×Ke + D/V×Kd×(1−t)', () => {
    expect(calcWaccAfterTax(40, 60, 11.5, 5, 25)).toBeCloseTo(8.4, 6)
  })

  it('D+E=0 时 WACC 为 0', () => {
    expect(calcWaccAfterTax(0, 0, 10, 5, 25)).toBe(0)
  })

  it('税前折现率 = 税后WACC/(1−t)', () => {
    expect(calcPreTaxDiscountRate(8.4, 25)).toBeCloseTo(11.2, 6)
  })
})

describe('H1-15 公允净额', () => {
  it('优先销售协议价', () => {
    const r = resolveFairValue(baseFv({
      salesAgreementPrice: 100,
      activeMarketPrice: 90,
      estimatedPrice: 80,
    }))
    expect(r.source).toBe('销售协议价格')
    expect(r.value).toBe(100)
  })

  it('无协议时取活跃市价', () => {
    const r = resolveFairValue(baseFv({ activeMarketPrice: 90, estimatedPrice: 80 }))
    expect(r.source).toBe('活跃市场价格')
    expect(r.value).toBe(90)
  })

  it('处置费用合计', () => {
    expect(calcDisposalTotal(baseFv({
      legalFees: 1, relatedTaxes: 2, transportCosts: 3, directCosts: 4, otherCosts: 5,
    }))).toBe(15)
  })

  it('可收回金额 = MAX(公允净额, DCF)', () => {
    const fvNet = 100 - 15
    const dcf = calcDcfPresentValue([30, 30, 30, 30, 30], 0.1)
      + calcTerminalValue(30 * 1.02, 0.1, 0.02) / Math.pow(1.1, 5)
    expect(Math.max(fvNet, dcf)).toBeGreaterThan(fvNet)
  })
})

describe('H1-15 终值单独敏感轴', () => {
  const cfs = [100, 100, 100, 100, 100]

  it('折现率轴：固定 g，r 升高则终值现值下降', () => {
    const axis = calcTerminalSensitivityAxis({
      cashFlows: cfs,
      baseRatePct: 10,
      baseGrowthPct: 2,
      terminalCashFlow: 0,
      fairValueLessDisposal: 0,
      axis: 'rate',
      offsetsPct: [-1, 0, 1],
    })
    expect(axis).toHaveLength(3)
    const valid = axis.filter((p) => !p.invalid)
    expect(valid[0].terminalValueDiscounted).toBeGreaterThan(valid[1].terminalValueDiscounted)
    expect(valid[1].terminalValueDiscounted).toBeGreaterThan(valid[2].terminalValueDiscounted)
  })

  it('增长率轴：固定 r，g 升高则终值现值上升', () => {
    const axis = calcTerminalSensitivityAxis({
      cashFlows: cfs,
      baseRatePct: 10,
      baseGrowthPct: 2,
      terminalCashFlow: 0,
      fairValueLessDisposal: 0,
      axis: 'growth',
      offsetsPct: [-0.5, 0, 0.5],
    })
    const valid = axis.filter((p) => !p.invalid)
    expect(valid[0].terminalValueDiscounted).toBeLessThan(valid[1].terminalValueDiscounted)
    expect(valid[1].terminalValueDiscounted).toBeLessThan(valid[2].terminalValueDiscounted)
  })

  it('r≤g 时标记 invalid 且终值为 0', () => {
    const axis = calcTerminalSensitivityAxis({
      cashFlows: cfs,
      baseRatePct: 3,
      baseGrowthPct: 2,
      terminalCashFlow: 0,
      fairValueLessDisposal: 0,
      axis: 'growth',
      offsetsPct: [2], // g=4% > r=3%
    })
    expect(axis[0].invalid).toBe(true)
    expect(axis[0].terminalValueDiscounted).toBe(0)
  })
})
