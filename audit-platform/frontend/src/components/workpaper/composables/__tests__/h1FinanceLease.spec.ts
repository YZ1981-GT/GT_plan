import { describe, it, expect } from 'vitest'
import {
  calcFinanceLeaseReceivable,
  calcUnearnedFinanceIncome,
  calcGrossLeaseInvestment,
  calcPvToFvRatio,
  calcLeaseNpv,
  buildFinanceLeaseAmortization,
  solveLeaseImplicitRatePct,
} from '../useH1FormulaEngine'
import { buildH1G5Reconcile, type H1FinanceLeaseG5Seed } from '../h1FinanceLeaseG5Pull'

describe('H1-20 融资租出公式', () => {
  it('应收融资租赁款 = 最低租赁收款额 + 初始直接费用', () => {
    expect(calcFinanceLeaseReceivable(1_000_000, 20_000)).toBe(1_020_000)
  })

  it('未确认融资收益含未担保余值', () => {
    expect(calcUnearnedFinanceIncome(1_000_000, 800_000)).toBe(200_000)
    expect(calcUnearnedFinanceIncome(1_000_000, 800_000, 50_000)).toBe(250_000)
  })

  it('毛投资额 = 收款额 + 未担保余值 + 初始直接费用', () => {
    expect(calcGrossLeaseInvestment(1_000_000, 50_000, 20_000)).toBe(1_070_000)
  })

  it('现值/公允占比 ≥90% 判定', () => {
    expect(calcPvToFvRatio(900_000, 1_000_000)).toBe(90)
    expect(calcPvToFvRatio(899_000, 1_000_000)).toBeCloseTo(89.9, 1)
    expect(calcPvToFvRatio(100, 0)).toBeNull()
  })

  it('实际利率法分配表：融资收入=期初净投资×利率', () => {
    const schedule = buildFinanceLeaseAmortization({
      openingNetInvestment: 100_000,
      annualRent: 26_380,
      implicitRatePct: 10,
      periodCount: 5,
      startYear: 2020,
    })
    expect(schedule).toHaveLength(5)
    expect(schedule[0].financeIncome).toBe(10_000)
    expect(schedule[0].netDecrease).toBe(16_380)
    expect(schedule[0].netBalance).toBe(83_620)
    expect(schedule[0].date).toBe('2020-12-31')
  })

  it('分配表末期末并入未担保余值', () => {
    const schedule = buildFinanceLeaseAmortization({
      openingNetInvestment: 100_000,
      annualRent: 20_000,
      implicitRatePct: 10,
      periodCount: 3,
      unguaranteedResidual: 50_000,
    })
    expect(schedule[0].rent).toBe(20_000)
    expect(schedule[2].rent).toBe(70_000) // 20000 + 50000
  })

  it('IRR 求解：等额租金使 NPV≈0', () => {
    // 已知：净投资 100000，年租 26380，5 期，利率约 10%
    const rate = solveLeaseImplicitRatePct({
      netInvestment: 100_000,
      annualRent: 26_380,
      periodCount: 5,
    })
    expect(rate).not.toBeNull()
    expect(rate!).toBeGreaterThan(9.5)
    expect(rate!).toBeLessThan(10.5)
    const npv = calcLeaseNpv({
      netInvestment: 100_000,
      annualRent: 26_380,
      periodCount: 5,
      rateDecimal: rate! / 100,
    })
    expect(Math.abs(npv)).toBeLessThan(50)
  })

  it('IRR 求解：含未担保余值', () => {
    const rate = solveLeaseImplicitRatePct({
      netInvestment: 100_000,
      annualRent: 20_000,
      periodCount: 5,
      unguaranteedResidual: 30_000,
    })
    expect(rate).not.toBeNull()
    expect(rate!).toBeGreaterThan(0)
    const npv = calcLeaseNpv({
      netInvestment: 100_000,
      annualRent: 20_000,
      periodCount: 5,
      rateDecimal: rate! / 100,
      unguaranteedResidual: 30_000,
    })
    expect(Math.abs(npv)).toBeLessThan(50)
  })

  it('现金流不足以覆盖净投资时返回 null', () => {
    expect(solveLeaseImplicitRatePct({
      netInvestment: 100_000,
      annualRent: 1_000,
      periodCount: 2,
    })).toBeNull()
  })
})

describe('H1-20 ↔ G5 勾稽', () => {
  it('按承租人+项目名匹配并计算差异', () => {
    const seeds: H1FinanceLeaseG5Seed[] = [{
      assetName: '设备A',
      lessee: '承租人甲',
      leaseStart: '2020-01-01',
      minLeasePayment: 1_000_000,
      initialDirectCosts: 0,
      unguaranteedResidual: 0,
      fairValue: 800_000,
      presentValue: 800_000,
      unrecognizedFinIncome: 200_000,
      allocRate: 10,
      annualRent: 200_000,
      periodCount: 5,
      g5BookNetInvestment: 790_000,
      g5BookUnearned: 210_000,
      g5ProjectName: '设备A',
      source: 'G5-5',
      remark: '',
    }]
    const rows = buildH1G5Reconcile([{
      rowId: 'r1',
      assetName: '设备A',
      lessee: '承租人甲',
      presentValue: 800_000,
      unrecognizedFinIncome: 200_000,
      allocRate: 10,
    }], seeds)
    expect(rows).toHaveLength(1)
    expect(rows[0].matched).toBe(true)
    expect(rows[0].netVariance).toBe(10_000)
    expect(rows[0].unearnedVariance).toBe(-10_000)
  })

  it('无匹配时 matched=false', () => {
    const rows = buildH1G5Reconcile([{
      rowId: 'r1',
      assetName: '设备B',
      lessee: '乙',
      presentValue: 1,
      unrecognizedFinIncome: 0,
      allocRate: 0,
    }], [])
    expect(rows[0].matched).toBe(false)
  })
})
