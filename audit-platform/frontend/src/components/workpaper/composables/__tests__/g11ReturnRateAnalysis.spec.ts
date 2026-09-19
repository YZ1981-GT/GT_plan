import { describe, it, expect } from 'vitest'
import {
  calcAverageBalance,
  calcReturnRate,
  calcReturnRateChange,
  isReturnRateChangeExceeding,
  calcAdjustedAmount,
  calcSubtotal,
} from '../useG11FormulaEngine'
import { mapAdjStoreToReturnRatePatch } from '../useG11ReturnRateAnalysis'
import {
  G11_RETURN_RATE_CHANGE_THRESHOLD,
  G11_RETURN_RATE_ITEMS,
  G11_RETURN_RATE_CONCLUSION_TEMPLATES,
} from '../g11Constants'
import { parseG11AdjStore } from '../g11AdjStorage'

describe('G11-4 收益率分析逻辑', () => {
  it('平均投资与收益率公式对齐源模板①/②/③', () => {
    const avg = calcAverageBalance(100, 300)
    expect(avg).toBe(200)
    expect(calcReturnRate(20, avg)).toBeCloseTo(0.1)
  })

  it('|变动⑦|>5pp 标记异常', () => {
    const change = calcReturnRateChange(0.12, 0.05)
    expect(change).toBeCloseTo(0.07)
    expect(isReturnRateChangeExceeding(change, G11_RETURN_RATE_CHANGE_THRESHOLD)).toBe(true)
    expect(isReturnRateChangeExceeding(0.04, G11_RETURN_RATE_CHANGE_THRESHOLD)).toBe(false)
  })

  it('平均余额为 0 时收益率 N/A（处置/一次性利得）', () => {
    expect(calcReturnRate(100, 0)).toBeNull()
    expect(calcReturnRateChange(0.1, null)).toBeNull()
  })

  it('默认项目与审定表行键一致，可从 G11-1 带入', () => {
    expect(G11_RETURN_RATE_ITEMS.length).toBeGreaterThanOrEqual(15)
    const store = parseG11AdjStore(JSON.stringify({
      equity_method: {
        currentUnadjusted: 100,
        currentAdjustment: 10,
        priorUnadjusted: 80,
        priorAdjustment: 0,
      },
    }))
    const patch = mapAdjStoreToReturnRatePatch('equity_method', store)
    expect(patch).toEqual({
      currentIncome: calcAdjustedAmount(100, 10),
      priorAudited: calcAdjustedAmount(80, 0),
    })
    expect(mapAdjStoreToReturnRatePatch('unknown_key', store)).toBeNull()
  })

  it('合计行 = 各分项发生额/审定求和，合计收益率用合计平均余额', () => {
    const incomes = [10, 20, 30]
    const openings = [100, 200, 0]
    const closings = [100, 200, 0]
    const totalIncome = calcSubtotal(incomes)
    const totalAvg = calcAverageBalance(calcSubtotal(openings), calcSubtotal(closings))
    expect(totalIncome).toBe(60)
    expect(totalAvg).toBe(300)
    expect(calcReturnRate(totalIncome, totalAvg)).toBeCloseTo(0.2)
  })

  it('结论模板齐全', () => {
    expect(G11_RETURN_RATE_CONCLUSION_TEMPLATES.length).toBe(3)
    expect(G11_RETURN_RATE_CONCLUSION_TEMPLATES.map((t) => t.key)).toContain('no_abnormal')
  })
})
