import { describe, expect, it } from 'vitest'
import {
  calcG7DetailSummary,
  createG7CostRow,
  createG7EquityRow,
  normalizeG7DetailRows,
  recalcG7CostRow,
  recalcG7EquityRow,
  syncG7ImpairmentRows,
  type G7DetailState,
} from '../g7DetailModel'

describe('G7-2 原表等价公式链', () => {
  it('成本法按未审、AJE、RJE形成审定期末', () => {
    const row = createG7CostRow(1, '子公司A')
    Object.assign(row, {
      openingRatio: 0.6,
      openingAmount: 100,
      increaseRatio: 0.1,
      increaseAmount: 30,
      decreaseRatio: 0.05,
      decreaseAmount: 10,
      openingAje: 5,
      openingRje: -2,
      ajeIncrease: 3,
      ajeDecrease: 1,
      rjeIncrease: 2,
      rjeDecrease: 4,
    })

    recalcG7CostRow(row)

    expect(row.closingAmount).toBe(120)
    expect(row.auditedOpeningAmount).toBe(103)
    expect(row.auditedIncreaseAmount).toBe(35)
    expect(row.auditedDecreaseAmount).toBe(15)
    expect(row.auditedClosingAmount).toBe(123)
    expect(row.auditedClosingRatio).toBeCloseTo(0.65)
  })

  it('权益法未审包含其他栏，原表BB审定期末排除其他栏', () => {
    const row = createG7EquityRow(1, '联营企业A', 'associate')
    Object.assign(row, {
      openingAmount: 100,
      costIncrease: 20,
      profitLossAdjustment: 8,
      otherComprehensiveIncome: 3,
      otherEquityChange: 2,
      otherIncrease: 50,
      costDecrease: 4,
      dividendReceived: 5,
      otherDecrease: 40,
      ajeProfitLoss: 2,
      rjeOci: 1,
    })

    recalcG7EquityRow(row)

    expect(row.equityIncreaseSubtotal).toBe(13)
    expect(row.closingAmount).toBe(134)
    expect(row.auditedEquityIncreaseSubtotal).toBe(16)
    expect(row.auditedClosingAmount).toBe(127)
  })

  it('减值行随投资单位生成，汇总形成1511、1512及净值', () => {
    const cost = createG7CostRow(1, '子公司A')
    cost.openingAmount = 100
    cost.increaseAmount = 20
    recalcG7CostRow(cost)
    const equity = createG7EquityRow(1, '合营企业A')
    equity.openingAmount = 50
    equity.profitLossAdjustment = 10
    recalcG7EquityRow(equity)
    const state: G7DetailState = { costRows: [cost], equityRows: [equity], impairmentRows: [] }

    syncG7ImpairmentRows(state)
    state.impairmentRows[0].openingAmount = 5
    state.impairmentRows[0].increaseAmount = 2
    syncG7ImpairmentRows(state)
    const summary = calcG7DetailSummary(state)

    expect(state.impairmentRows).toHaveLength(2)
    expect(summary.gross.closing).toBe(180)
    expect(summary.impairment.closing).toBe(7)
    expect(summary.net.closing).toBe(173)
  })

  it('兼容迁移旧版通用54字段数据', () => {
    const state = normalizeG7DetailRows([{
      investeeName: '旧版联营企业',
      controlType: 'associate',
      openingInvestCost: 80,
      openingEquityAdj: 20,
      holdingRatio: 0.3,
      increaseNewInvest: 5,
      increaseEquityMethod: 6,
      profitDistribution: 2,
    }])

    expect(state.equityRows).toHaveLength(1)
    expect(state.equityRows[0].relationship).toBe('associate')
    expect(state.equityRows[0].openingAmount).toBe(100)
    expect(state.equityRows[0].closingAmount).toBe(109)
    expect(state.impairmentRows).toHaveLength(1)
  })
})
