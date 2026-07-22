/**
 * H1-12 折旧测算引擎 — 对齐 Excel 底稿（不含/含/多次减值）单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcStraightLine,
  calcMonthsDepreciated,
  calcStraightLineTest,
  calcWithImpairmentTest,
  calcMultiImpairmentTest,
  calcDepreciationWithImpairment,
  recommendDepreciationBranch,
  calcFullDepreciationDate,
} from '../useH1DepreciationEngine'

describe('calcMonthsDepreciated (CAS 次月起提)', () => {
  it('同年内：1月投入 → 12月末已提 11 月', () => {
    expect(calcMonthsDepreciated('2020-01-15', '2020-12-31', 120)).toBe(11)
  })

  it('跨年：1月投入 → 次年12月末已提 23 月', () => {
    expect(calcMonthsDepreciated('2020-01-15', '2021-12-31', 120)).toBe(23)
  })

  it('投入当月不提：1月投入 → 1月末已提 0', () => {
    expect(calcMonthsDepreciated('2020-01-15', '2020-01-31', 120)).toBe(0)
  })

  it('不超过使用月限', () => {
    expect(calcMonthsDepreciated('2010-01-01', '2025-12-31', 60)).toBe(60)
  })
})

describe('calcStraightLineTest (H1-12A)', () => {
  it('满年资产：本期12月，月折旧正确', () => {
    const r = calcStraightLineTest({
      cost: 120000,
      salvageRate: 0.05,
      usefulLifeYears: 10,
      startDate: '2015-01-01',
      periodBegin: '2024-01-01',
      periodEnd: '2024-12-31',
      bookMonthly: 950,
      bookAccDepEnd: 114000,
    })
    expect(r.calcMonthly).toBe(950) // 120000*0.95/10/12
    expect(r.usefulLifeMonths).toBe(120)
    expect(r.periodMonths).toBe(12)
    expect(r.periodDep).toBe(11400)
    expect(r.monthlyDiff).toBe(0)
  })

  it('满折日可生成', () => {
    const d = calcFullDepreciationDate('2020-01-15', 60)
    expect(d).toMatch(/^2025-/)
  })
})

describe('calcWithImpairmentTest (H1-12B)', () => {
  it('期中减值：本期拆分减值前/后月数', () => {
    // 2018-01 投入，2024-06-30 减值 20000，截止 2024-12-31
    const r = calcWithImpairmentTest({
      cost: 240000,
      salvageRate: 0,
      usefulLifeYears: 10,
      startDate: '2018-01-01',
      periodBegin: '2024-01-01',
      periodEnd: '2024-12-31',
      impairmentAmount: 20000,
      impairmentDate: '2024-06-30',
    })
    // 原月折旧 = 240000/120 = 2000
    expect(r.preImpairmentMonthly).toBe(2000)
    expect(r.monthsBeforeImpairmentInPeriod + r.monthsAfterImpairmentInPeriod).toBe(r.periodMonths)
    expect(r.monthsBeforeImpairmentInPeriod).toBeGreaterThan(0)
    expect(r.monthsAfterImpairmentInPeriod).toBeGreaterThan(0)
    expect(r.postImpairmentMonthly).toBeLessThan(r.preImpairmentMonthly)
    // 本期 = 前×旧 + 后×新
    const expected = r.preImpairmentMonthly * r.monthsBeforeImpairmentInPeriod
      + r.postImpairmentMonthly * r.monthsAfterImpairmentInPeriod
    expect(r.periodDep).toBeCloseTo(expected, 1)
  })

  it('减值后月折旧扣除累计折旧与残值', () => {
    const monthly = calcDepreciationWithImpairment(120000, 0.05, 10, 10000, 24)
    // acc=950*24=22800; carrying=87200; rem=81200; /96
    expect(monthly).toBeCloseTo(81200 / 96, 5)
  })
})

describe('calcMultiImpairmentTest (H1-12C)', () => {
  it('两次减值生成多段', () => {
    const r = calcMultiImpairmentTest({
      cost: 240000,
      salvageRate: 0,
      usefulLifeYears: 10,
      startDate: '2018-01-01',
      periodBegin: '2024-01-01',
      periodEnd: '2024-12-31',
      events: [
        { eventDate: '2022-06-30', amount: 10000 },
        { eventDate: '2024-03-31', amount: 5000 },
      ],
    })
    expect(r.segments.length).toBeGreaterThanOrEqual(3)
    expect(r.periodDep).toBeGreaterThan(0)
    // 后段月折旧应低于最初段
    expect(r.segments[r.segments.length - 1].monthly).toBeLessThanOrEqual(r.segments[0].monthly)
  })
})

describe('recommendDepreciationBranch 联动', () => {
  it('无减值 → A', () => {
    expect(recommendDepreciationBranch({})).toBe('A')
  })
  it('期末减值 → B', () => {
    expect(recommendDepreciationBranch({ impairmentEnd: 1000 })).toBe('B')
  })
  it('多次事件 → C', () => {
    expect(recommendDepreciationBranch({ impairmentEventCount: 2 })).toBe('C')
  })
})

describe('calcStraightLine 基础', () => {
  it('标准公式', () => {
    expect(calcStraightLine(120000, 0.05, 10)).toBe(950)
  })
})
