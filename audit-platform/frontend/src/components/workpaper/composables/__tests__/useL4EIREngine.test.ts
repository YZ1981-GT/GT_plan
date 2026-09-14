/**
 * 单元测试 — L4 应付债券 实际利率法引擎
 *
 * 验证核心纯函数的数学正确性，使用典型债券场景。
 * Spec: .kiro/specs/l4-bonds-payable/ Requirements 4.4-4.7, 9.1-9.6
 */
import { describe, it, expect } from 'vitest'
import {
  calcInterestExpense,
  calcEndAmortizedCost_Bullet,
  calcEndAmortizedCost_Installment,
  generateSchedule,
  validateSchedule,
  solveEIR,
} from '../useL4EIREngine'

describe('useL4EIREngine — calcInterestExpense', () => {
  it('基础计算: 1,000,000 × 5% = 50,000', () => {
    expect(calcInterestExpense(1_000_000, 0.05)).toBeCloseTo(50_000, 2)
  })

  it('EIR=0 时利息费用为 0（不产生 NaN）', () => {
    expect(calcInterestExpense(1_000_000, 0)).toBe(0)
    expect(calcInterestExpense(0, 0)).toBe(0)
  })

  it('小利率精度验证: 500,000 × 0.0345 = 17,250', () => {
    expect(calcInterestExpense(500_000, 0.0345)).toBeCloseTo(17_250, 2)
  })
})

describe('useL4EIREngine — calcEndAmortizedCost_Bullet', () => {
  it('期末 = 期初 + 利息费用（利息资本化）', () => {
    expect(calcEndAmortizedCost_Bullet(980_000, 49_000)).toBe(1_029_000)
  })

  it('利息为 0 时期末=期初', () => {
    expect(calcEndAmortizedCost_Bullet(1_000_000, 0)).toBe(1_000_000)
  })
})

describe('useL4EIREngine — calcEndAmortizedCost_Installment', () => {
  it('期末 = 期初 + 利息费用 - 实付利息', () => {
    // 折价场景：期初 980,000, 利息费用 49,000, 票面利息 40,000
    // 期末 = 980,000 + 49,000 - 40,000 = 989,000
    expect(calcEndAmortizedCost_Installment(980_000, 49_000, 40_000)).toBe(989_000)
  })

  it('溢价场景：利息费用 < 票面利息，摊余成本递减', () => {
    // 期初 1,050,000, 利息费用 42,000, 票面利息 50,000
    // 期末 = 1,050,000 + 42,000 - 50,000 = 1,042,000
    expect(calcEndAmortizedCost_Installment(1_050_000, 42_000, 50_000)).toBe(1_042_000)
  })
})

describe('useL4EIREngine — generateSchedule（installment 分支）', () => {
  it('折价发行5年：期末摊余成本趋向面值', () => {
    // 面值 1,000,000，发行价(初始摊余成本) 920,000，票面利率 4%，实际利率 6%，5年
    const schedule = generateSchedule(920_000, 1_000_000, 0.04, 0.06, 5, 'installment')

    expect(schedule).toHaveLength(5)
    expect(schedule[0].period).toBe(1)
    expect(schedule[0].beginCost).toBe(920_000)
    expect(schedule[0].couponInterest).toBeCloseTo(40_000, 2)
    expect(schedule[0].interestExpense).toBeCloseTo(55_200, 2) // 920000 × 0.06
    expect(schedule[0].amortization).toBeCloseTo(15_200, 2) // 55200 - 40000
    expect(schedule[0].endCost).toBeCloseTo(935_200, 2) // 920000 + 55200 - 40000

    // 最后一期 endCost 强制 = faceValue
    expect(schedule[4].endCost).toBe(1_000_000)
  })

  it('溢价发行3年：期末摊余成本递减趋向面值', () => {
    // 面值 1,000,000，发行价 1,080,000，票面利率 6%，实际利率 3%，3年
    const schedule = generateSchedule(1_080_000, 1_000_000, 0.06, 0.03, 3, 'installment')

    expect(schedule).toHaveLength(3)
    // 第一期：利息费用 = 1,080,000 × 0.03 = 32,400 < 票面利息 60,000
    expect(schedule[0].interestExpense).toBeCloseTo(32_400, 2)
    expect(schedule[0].amortization).toBeCloseTo(-27_600, 2) // 负=溢价摊销
    // 期末递减
    expect(schedule[0].endCost).toBeLessThan(schedule[0].beginCost)
    // 最后一期 endCost = faceValue
    expect(schedule[2].endCost).toBe(1_000_000)
  })

  it('periods=0 返回空数组', () => {
    expect(generateSchedule(100, 100, 0.05, 0.05, 0, 'installment')).toEqual([])
  })

  it('EIR=0 + couponRate=0（零息）：所有利息为0，endCost不变', () => {
    const schedule = generateSchedule(1_000_000, 1_000_000, 0, 0, 3, 'installment')
    expect(schedule).toHaveLength(3)
    for (const row of schedule) {
      expect(row.interestExpense).toBe(0)
      expect(row.couponInterest).toBe(0)
      expect(row.amortization).toBe(0)
    }
    expect(schedule[2].endCost).toBe(1_000_000)
  })
})

describe('useL4EIREngine — generateSchedule（bullet 分支）', () => {
  it('到期一次还本付息：摊余成本逐期递增', () => {
    // 面值 1,000,000，发行价 950,000，票面利率 5%，实际利率 7%，3年
    const schedule = generateSchedule(950_000, 1_000_000, 0.05, 0.07, 3, 'bullet')

    expect(schedule).toHaveLength(3)
    expect(schedule[0].beginCost).toBe(950_000)
    // 利息费用 = 950,000 × 0.07 = 66,500
    expect(schedule[0].interestExpense).toBeCloseTo(66_500, 2)
    // bullet: endCost = begin + interestExpense（利息全滚入）
    expect(schedule[0].endCost).toBeCloseTo(1_016_500, 2)
    // 每期递增
    expect(schedule[1].beginCost).toBeCloseTo(schedule[0].endCost, 2)
    expect(schedule[2].endCost).toBeGreaterThan(schedule[1].endCost)
  })
})

describe('useL4EIREngine — validateSchedule', () => {
  it('installment 分支尾差调整后 isValid=true', () => {
    const schedule = generateSchedule(920_000, 1_000_000, 0.04, 0.06, 5, 'installment')
    const result = validateSchedule(schedule, 1_000_000)
    expect(result.isValid).toBe(true)
    expect(result.tailDiff).toBe(0) // 强制调整后精确为0
  })

  it('空摊销表 isValid=false', () => {
    const result = validateSchedule([], 1_000_000)
    expect(result.isValid).toBe(false)
  })

  it('bullet 分支 endCost 远大于面值（信息性 tailDiff）', () => {
    const schedule = generateSchedule(950_000, 1_000_000, 0.05, 0.07, 3, 'bullet')
    const result = validateSchedule(schedule, 1_000_000)
    // bullet 最终 endCost > faceValue（含累积利息），isValid 可能 false
    expect(result.tailDiff).toBeGreaterThan(0)
  })
})

describe('useL4EIREngine — solveEIR', () => {
  it('已知场景求解：面值100万/票面5%/5年/发行价920,000', () => {
    // 分期付息：5年每年付 50,000，最后一期额外归还本金 1,000,000
    const cashFlows = [50_000, 50_000, 50_000, 50_000, 1_050_000]
    const initialAmount = 920_000
    const eir = solveEIR(cashFlows, initialAmount)

    // 理论EIR约为 7.0%
    expect(eir).toBeGreaterThan(0.06)
    expect(eir).toBeLessThan(0.08)

    // 验证：以求解的EIR折现应≈初始金额
    let pv = 0
    for (let i = 0; i < cashFlows.length; i++) {
      pv += cashFlows[i] / Math.pow(1 + eir, i + 1)
    }
    expect(pv).toBeCloseTo(initialAmount, 2)
  })

  it('平价发行（cashFlows现值=初始金额，EIR=票面利率）', () => {
    // 面值100，票面10%，3年，平价发行100
    const cashFlows = [10, 10, 110]
    const eir = solveEIR(cashFlows, 100)
    expect(eir).toBeCloseTo(0.1, 4) // 应精确为 10%
  })

  it('空现金流返回 0', () => {
    expect(solveEIR([], 100)).toBe(0)
  })

  it('initialAmount=0 返回 0', () => {
    expect(solveEIR([100, 100], 0)).toBe(0)
  })

  it('高溢价发行（低EIR场景）', () => {
    // 面值100，票面8%，5年，溢价发行115
    const cashFlows = [8, 8, 8, 8, 108]
    const eir = solveEIR(cashFlows, 115)
    // EIR < 票面利率 8%
    expect(eir).toBeLessThan(0.08)
    expect(eir).toBeGreaterThan(0.01)
  })
})
