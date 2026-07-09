/**
 * Unit Tests — H2 利息资本化引擎
 * Spec: .kiro/specs/h2-construction-in-progress/ Task 2.2
 */
import { describe, it, expect } from 'vitest'
import {
  calcWeightedCapRate,
  calcWeightedExpenditure,
  calcCapAmountNoBorrow,
  calcSpecialLoanCap,
  calcGeneralLoanSupp,
  calcTotalCapWithBorrow,
  calcDcfPresentValue,
  calcTerminalValue,
} from '../composables/useH2InterestCapEngine'

describe('useH2InterestCapEngine — 加权资本化率', () => {
  it('单笔借款时返回该笔利率', () => {
    const loans = [{ principal: 1_000_000, rate: 0.05, days: 365 }]
    expect(calcWeightedCapRate(loans)).toBeCloseTo(0.05, 10)
  })

  it('两笔等额等期借款时返回利率算术平均', () => {
    const loans = [
      { principal: 1_000_000, rate: 0.04, days: 365 },
      { principal: 1_000_000, rate: 0.06, days: 365 },
    ]
    expect(calcWeightedCapRate(loans)).toBeCloseTo(0.05, 10)
  })

  it('不同天数加权：占用天数长的利率权重更高', () => {
    const loans = [
      { principal: 1_000_000, rate: 0.04, days: 100 },
      { principal: 1_000_000, rate: 0.06, days: 300 },
    ]
    // weight1 = 1e6 * 100/365, weight2 = 1e6 * 300/365
    // rate = (w1*0.04 + w2*0.06) / (w1+w2) = (100*0.04 + 300*0.06)/400 = (4+18)/400 = 0.055
    expect(calcWeightedCapRate(loans)).toBeCloseTo(0.055, 10)
  })

  it('空数组返回0', () => {
    expect(calcWeightedCapRate([])).toBe(0)
  })

  it('所有天数为0返回0', () => {
    const loans = [{ principal: 1_000_000, rate: 0.05, days: 0 }]
    expect(calcWeightedCapRate(loans)).toBe(0)
  })
})

describe('useH2InterestCapEngine — 累计支出加权平均数', () => {
  it('单笔支出占满全期返回该金额', () => {
    const expenditures = [{ amount: 500_000, days: 365 }]
    expect(calcWeightedExpenditure(expenditures, 365)).toBeCloseTo(500_000, 5)
  })

  it('单笔支出占半期返回半额', () => {
    const expenditures = [{ amount: 1_000_000, days: 180 }]
    // 1_000_000 * 180 / 360 = 500_000
    expect(calcWeightedExpenditure(expenditures, 360)).toBeCloseTo(500_000, 5)
  })

  it('多笔支出加权求和', () => {
    const expenditures = [
      { amount: 100_000, days: 300 },
      { amount: 200_000, days: 200 },
    ]
    // (100000*300 + 200000*200) / 365 = (30000000 + 40000000) / 365 ≈ 191780.82
    expect(calcWeightedExpenditure(expenditures, 365)).toBeCloseTo(70_000_000 / 365, 2)
  })

  it('totalDays=0返回0', () => {
    const expenditures = [{ amount: 500_000, days: 180 }]
    expect(calcWeightedExpenditure(expenditures, 0)).toBe(0)
  })

  it('空支出数组返回0', () => {
    expect(calcWeightedExpenditure([], 365)).toBe(0)
  })
})

describe('useH2InterestCapEngine — 无专门借款资本化金额', () => {
  it('累计支出加权 × 资本化率', () => {
    expect(calcCapAmountNoBorrow(500_000, 0.05)).toBeCloseTo(25_000, 5)
  })

  it('任一为0时返回0', () => {
    expect(calcCapAmountNoBorrow(0, 0.05)).toBe(0)
    expect(calcCapAmountNoBorrow(500_000, 0)).toBe(0)
  })
})

describe('useH2InterestCapEngine — 专门借款资本化', () => {
  it('利息 - 闲置收益', () => {
    expect(calcSpecialLoanCap(100_000, 20_000)).toBe(80_000)
  })

  it('闲置收益为0时返回全部利息', () => {
    expect(calcSpecialLoanCap(100_000, 0)).toBe(100_000)
  })
})

describe('useH2InterestCapEngine — 一般借款补充资本化', () => {
  it('超额加权支出 × 一般借款利率', () => {
    expect(calcGeneralLoanSupp(200_000, 0.06)).toBeCloseTo(12_000, 5)
  })

  it('超额为0时返回0', () => {
    expect(calcGeneralLoanSupp(0, 0.06)).toBe(0)
  })
})

describe('useH2InterestCapEngine — 有专门借款合计', () => {
  it('专门 + 一般', () => {
    expect(calcTotalCapWithBorrow(80_000, 12_000)).toBe(92_000)
  })
})

describe('useH2InterestCapEngine — DCF现值', () => {
  it('单期现金流折现', () => {
    // 100 / (1+0.1)^1 = 90.909...
    expect(calcDcfPresentValue([100], 0.1)).toBeCloseTo(90.9091, 3)
  })

  it('多期现金流折现', () => {
    // 100/(1.1) + 200/(1.1^2) + 300/(1.1^3)
    // = 90.909 + 165.289 + 225.394 = 481.593
    const expected = 100 / 1.1 + 200 / (1.1 ** 2) + 300 / (1.1 ** 3)
    expect(calcDcfPresentValue([100, 200, 300], 0.1)).toBeCloseTo(expected, 3)
  })

  it('空数组返回0', () => {
    expect(calcDcfPresentValue([], 0.1)).toBe(0)
  })

  it('折现率≤0返回0', () => {
    expect(calcDcfPresentValue([100, 200], 0)).toBe(0)
    expect(calcDcfPresentValue([100, 200], -0.05)).toBe(0)
  })
})

describe('useH2InterestCapEngine — 终值（Gordon模型）', () => {
  it('perpetuityCF / (discountRate - growthRate)', () => {
    // 100 / (0.1 - 0.03) = 100 / 0.07 ≈ 1428.57
    expect(calcTerminalValue(100, 0.1, 0.03)).toBeCloseTo(1428.5714, 2)
  })

  it('discountRate == growthRate时返回0（无效模型）', () => {
    expect(calcTerminalValue(100, 0.1, 0.1)).toBe(0)
  })

  it('discountRate < growthRate时返回0（无效模型）', () => {
    expect(calcTerminalValue(100, 0.05, 0.1)).toBe(0)
  })

  it('growthRate=0时退化为perpetuity', () => {
    // 100 / (0.1 - 0) = 1000
    expect(calcTerminalValue(100, 0.1, 0)).toBeCloseTo(1000, 5)
  })
})
