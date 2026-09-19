/**
 * H10-2 → H10-1 明细汇总带入
 */
import { describe, it, expect } from 'vitest'
import { defaultH10AdjStore } from '../h10AdjStorage'
import {
  aggregateH10DetailByAdjRowKey,
  applyH10DetailToAdjStore,
} from '../h10FillFromDetail'

describe('h10FillFromDetail', () => {
  it('按来源底稿汇总到审定行（H8→使用权、I1→无形）', () => {
    const totals = aggregateH10DetailByAdjRowKey([
      { sourceWp: 'H1', disposalGainLoss: 100 },
      { sourceWp: 'H6', disposalGainLoss: 50 },
      { sourceWp: 'H8', disposalGainLoss: 30 },
      { sourceWp: 'I1', disposalGainLoss: 20 },
      { sourceWp: 'OTHER', disposalGainLoss: 999 },
    ])
    expect(totals.fixed_asset_disposal).toBe(150)
    expect(totals.rou_disposal).toBe(30)
    expect(totals.intangible_disposal).toBe(20)
    expect(totals.debt_restructuring_disposal).toBeUndefined()
  })

  it('写入未审并保留 AJE/RJE；试运行净额回写', () => {
    const store = defaultH10AdjStore()
    store.fixed_asset_disposal = {
      ...store.fixed_asset_disposal,
      currentAje: 10,
      currentRje: -2,
    }
    const result = applyH10DetailToAdjStore(
      store,
      [
        { sourceWp: 'H1', disposalGainLoss: 100 },
        { sourceWp: 'H2', disposalGainLoss: 40 },
      ],
      [
        { currentIncome: 80, currentCost: 30, priorIncome: 20, priorCost: 5 },
      ],
    )
    expect(result.nextStore.fixed_asset_disposal?.currentUnadjusted).toBe(100)
    expect(result.nextStore.fixed_asset_disposal?.currentAje).toBe(10)
    expect(result.nextStore.fixed_asset_disposal?.currentRje).toBe(-2)
    expect(result.nextStore.construction_disposal?.currentUnadjusted).toBe(40)
    expect(result.nextStore.trial_operation_sales?.currentUnadjusted).toBe(50)
    expect(result.nextStore.trial_operation_sales?.priorUnadjusted).toBe(15)
    expect(result.filledKeys).toEqual(
      expect.arrayContaining(['fixed_asset_disposal', 'construction_disposal', 'trial_operation_sales']),
    )
  })
})
