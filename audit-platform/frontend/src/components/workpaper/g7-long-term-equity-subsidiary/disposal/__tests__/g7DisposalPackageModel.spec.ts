import { describe, expect, it } from 'vitest'
import {
  calculatePackageRow,
  createPackageRow,
  validatePackageRows,
} from '../g7DisposalPackageModel'

describe('G7-12 原底稿公式链', () => {
  it('按原持股比例分摊应转出长投并计算重新计量损益', () => {
    const row = createPackageRow(1)
    Object.assign(row, {
      originalShareholdingRatio: 0.8,
      disposalRatio: 0.5,
      individualBookValue: 800,
      residualFairValue: 360,
    })

    const result = calculatePackageRow(row)
    expect(result.remainingRatio).toBe(0.3)
    expect(result.disposedBookValue).toBe(500)
    expect(result.residualBookValue).toBe(300)
    expect(result.remeasurementGain).toBe(60)
  })

  it('按CAS33口径计算合并处置损益', () => {
    const row = createPackageRow(1)
    Object.assign(row, {
      transactionPrice: 900,
      residualFairValue: 360,
      consolidatedNetAssets: 1000,
      goodwill: 50,
      consolidatedRecyclableOci: 20,
      priorStepDifference: 10,
    })

    expect(calculatePackageRow(row).consolidatedGain).toBe(240)
  })

  it('权益法追溯调整区按90%/10%拆分以前年度损益', () => {
    const row = createPackageRow(1)
    Object.assign(row, {
      equityMethodRatio: 0.3,
      preDisposalProfit: 100,
      currentProfit: 20,
      otherComprehensiveIncome: 10,
      otherEquityChanges: 5,
    })

    const result = calculatePackageRow(row)
    expect(result.openingRetainedEarnings).toBe(27)
    expect(result.surplusReserve).toBe(3)
    expect(result.investmentIncome).toBe(6)
    expect(result.longTermInvestmentOci).toBe(3)
    expect(result.longTermInvestmentOtherChanges).toBe(1.5)
  })
})

describe('G7-12 编制完整性校验', () => {
  it('阻断只有结论、没有判断依据和证据的底稿', () => {
    const row = createPackageRow(1)
    Object.assign(row, {
      investeeName: '甲公司',
      transactionPrice: 100,
      packageJudgmentConclusion: 'yes',
    })

    const errors = validatePackageRows([row])
    expect(errors.some((message) => message.includes('判断依据'))).toBe(true)
    expect(errors.some((message) => message.includes('丧失控制权'))).toBe(true)
    expect(errors.some((message) => message.includes('查验资料'))).toBe(true)
    expect(errors.some((message) => message.includes('四项判断'))).toBe(true)
  })
})
