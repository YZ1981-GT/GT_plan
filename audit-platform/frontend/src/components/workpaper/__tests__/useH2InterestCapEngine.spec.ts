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
  calcWeightedPrincipal,
  calcCapRateFromActualInterest,
  calcMonthlyWeightedExpChain,
  calcExpTotal,
  annualRateToMonthly,
  calcExcessWeightedExp,
  calcCapDiffRate,
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

describe('useH2InterestCapEngine — 本金加权与账面倒算利率（xlsx H2-10）', () => {
  it('本金加权平均数 = 本金×计息天数/当期天数', () => {
    expect(calcWeightedPrincipal(1_000_000, 180, 360)).toBeCloseTo(500_000, 5)
  })

  it('当期天数为0返回0', () => {
    expect(calcWeightedPrincipal(1_000_000, 180, 0)).toBe(0)
  })

  it('资本化率 = Σ实际利息 / Σ本金加权', () => {
    const loans = [
      { weightedPrincipal: 500_000, actualInterest: 20_000 },
      { weightedPrincipal: 500_000, actualInterest: 30_000 },
    ]
    expect(calcCapRateFromActualInterest(loans)).toBeCloseTo(0.05, 10)
  })

  it('本金加权合计为0返回0', () => {
    expect(calcCapRateFromActualInterest([{ weightedPrincipal: 0, actualInterest: 100 }])).toBe(0)
  })
})

describe('useH2InterestCapEngine — 月度加权支出链（半月平均法）', () => {
  it('工程支出合计', () => {
    expect(calcExpTotal({
      prelimDev: 10, engCost: 20, borrowCost: 5, install: 30, land: 15,
      decrease: 0, prepaid: 0,
    })).toBe(80)
  })

  it('年初加权 = 支出合计+预付-借款费用；次月滚动半月平均', () => {
    const opening = {
      prelimDev: 100, engCost: 0, borrowCost: 10, install: 0, land: 0,
      decrease: 0, prepaid: 20,
    }
    const months = [
      {
        prelimDev: 0, engCost: 40, borrowCost: 0, install: 0, land: 0,
        decrease: 0, prepaid: 0,
      },
    ]
    const chain = calcMonthlyWeightedExpChain(opening, months)
    expect(chain.openingWeighted).toBeCloseTo(120, 5)
    expect(chain.monthlyWeighted[0]).toBeCloseTo(140, 5)
  })

  it('年利率转月利率 /12', () => {
    expect(annualRateToMonthly(0.06)).toBeCloseTo(0.005, 10)
  })
})

describe('useH2InterestCapEngine — 累计支出加权平均数', () => {
  it('单笔支出占满全期返回该金额', () => {
    const expenditures = [{ amount: 500_000, days: 365 }]
    expect(calcWeightedExpenditure(expenditures, 365)).toBeCloseTo(500_000, 5)
  })

  it('单笔支出占半期返回半额', () => {
    const expenditures = [{ amount: 1_000_000, days: 180 }]
    expect(calcWeightedExpenditure(expenditures, 360)).toBeCloseTo(500_000, 5)
  })

  it('多笔支出加权求和', () => {
    const expenditures = [
      { amount: 100_000, days: 300 },
      { amount: 200_000, days: 200 },
    ]
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

  it('闲置收益超过利息时下限为0', () => {
    expect(calcSpecialLoanCap(10_000, 20_000)).toBe(0)
  })
})

describe('useH2InterestCapEngine — 一般借款补充资本化', () => {
  it('超额加权支出 × 一般借款利率', () => {
    expect(calcGeneralLoanSupp(200_000, 0.06)).toBeCloseTo(12_000, 5)
  })

  it('超额为0时返回0', () => {
    expect(calcGeneralLoanSupp(0, 0.06)).toBe(0)
  })

  it('利率为0时返回0', () => {
    expect(calcGeneralLoanSupp(200_000, 0)).toBe(0)
  })
})

describe('useH2InterestCapEngine — 超额与差异率', () => {
  it('calcExcessWeightedExp / calcCapDiffRate', () => {
    expect(calcExcessWeightedExp(500_000, 300_000)).toBe(200_000)
    expect(calcExcessWeightedExp(200_000, 300_000)).toBe(0)
    expect(calcCapDiffRate(100, 0)).toBeNull()
    expect(calcCapDiffRate(100, 1000)).toBeCloseTo(0.1, 10)
  })
})

describe('useH2InterestCapEngine — 有专门借款合计', () => {
  it('专门 + 一般', () => {
    expect(calcTotalCapWithBorrow(80_000, 12_000)).toBe(92_000)
  })
})

describe('useH2InterestCapEngine — 月度加权链(含SP)', () => {
  it('H2-11 扣减专门借款占用额', () => {
    const opening = {
      prelimDev: 100, engCost: 0, borrowCost: 0, install: 0, land: 0,
      decrease: 0, prepaid: 0, specialLoanUsed: 40,
    }
    const months = [{
      prelimDev: 60, engCost: 0, borrowCost: 0, install: 0, land: 0,
      decrease: 0, prepaid: 0, specialLoanUsed: 20,
    }]
    const noSp = calcMonthlyWeightedExpChain(opening, months, false)
    const withSp = calcMonthlyWeightedExpChain(opening, months, true)
    expect(noSp.openingWeighted).toBe(100)
    expect(withSp.openingWeighted).toBe(60)
    expect(withSp.monthlyWeighted[0]).toBe(80)
  })

  it('负基数下限为0', () => {
    const opening = {
      prelimDev: 10, engCost: 0, borrowCost: 0, install: 0, land: 0,
      decrease: 0, prepaid: 0, specialLoanUsed: 50,
    }
    expect(calcMonthlyWeightedExpChain(opening, [], true).openingWeighted).toBe(0)
  })
})

describe('useH2InterestCapEngine — DCF现值', () => {
  it('单期现金流折现', () => {
    expect(calcDcfPresentValue([100], 0.1)).toBeCloseTo(90.9091, 3)
  })

  it('多期现金流折现', () => {
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
    expect(calcTerminalValue(100, 0.1, 0.03)).toBeCloseTo(1428.5714, 2)
  })

  it('discountRate == growthRate时返回0（无效模型）', () => {
    expect(calcTerminalValue(100, 0.1, 0.1)).toBe(0)
  })

  it('discountRate < growthRate时返回0（无效模型）', () => {
    expect(calcTerminalValue(100, 0.05, 0.1)).toBe(0)
  })

  it('growthRate=0时退化为perpetuity', () => {
    expect(calcTerminalValue(100, 0.1, 0)).toBeCloseTo(1000, 5)
  })
})
