/**
 * H3-7 折旧测算引擎测试 — 对齐 Excel 底稿公式
 */
import { describe, it, expect } from 'vitest'
import {
  calcStraightLineTest,
  calcWithImpairmentTest,
} from '../useH3DepreciationEngine'

describe('H3-7 不含减值直线法', () => {
  it('月折旧 = 原值×(1-残值率)/年限/12', () => {
    const r = calcStraightLineTest({
      cost: 1_200_000,
      salvageRate: 0.05,
      usefulLifeYears: 20,
      startDate: '2020-01-15',
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
      bookMonthly: 4_750,
      bookAccDepEnd: 285_000,
    })
    expect(r.calcMonthly).toBeCloseTo(4750, 0)
    expect(r.periodMonths).toBe(12)
    expect(r.periodDep).toBeCloseTo(57000, 0)
    expect(r.monthlyDiff).toBeCloseTo(0, 0)
  })

  it('累计折旧差异 = 账面累计 - 测算累计', () => {
    const r = calcStraightLineTest({
      cost: 1_200_000,
      salvageRate: 0.05,
      usefulLifeYears: 20,
      startDate: '2020-01-15',
      periodEnd: '2025-12-31',
      bookAccDepEnd: 290_000,
    })
    expect(r.accDepDiff).toBeCloseTo(290_000 - r.calcAccDep, 0)
  })
})

describe('H3-7 含减值分段计提', () => {
  it('本期折旧 = 减值前月数×原月折旧 + 减值后月数×新月折旧', () => {
    const r = calcWithImpairmentTest({
      cost: 1_200_000,
      salvageRate: 0.05,
      usefulLifeYears: 20,
      startDate: '2020-01-15',
      periodBegin: '2025-01-01',
      periodEnd: '2025-12-31',
      impairmentAmount: 100_000,
      impairmentDate: '2025-06-30',
      bookMonthly: 3_800,
      bookAccDepEnd: 320_000,
    })
    expect(r.preImpairmentMonthly).toBeGreaterThan(0)
    expect(r.postImpairmentMonthly).toBeGreaterThan(0)
    expect(r.postImpairmentMonthly).toBeLessThan(r.preImpairmentMonthly)
    expect(r.periodDep).toBeCloseTo(
      r.preImpairmentMonthly * r.monthsBeforeImpairmentInPeriod
      + r.postImpairmentMonthly * r.monthsAfterImpairmentInPeriod,
      0,
    )
    expect(r.monthsBeforeImpairmentInPeriod + r.monthsAfterImpairmentInPeriod).toBe(r.periodMonths)
  })

  it('无减值金额时退化为直线法', () => {
    const r = calcWithImpairmentTest({
      cost: 600_000,
      salvageRate: 0.05,
      usefulLifeYears: 10,
      startDate: '2022-03-01',
      periodEnd: '2025-12-31',
      impairmentAmount: 0,
    })
    expect(r.postImpairmentMonthly).toBe(r.preImpairmentMonthly)
    expect(r.monthsAfterImpairmentInPeriod).toBe(0)
  })
})
