import { describe, it, expect } from 'vitest'
import {
  applyG1AdjustmentWriteback,
  allocateG1WritebackAcrossRows,
  listG1WritebackAllocTargets,
  G1_ADJ_WRITEBACK_ROW_KEY,
} from '../g1AdjudicationItems'

describe('G1-1 回写分摊', () => {
  it('默认回写到 cost-trading-other', () => {
    const store = applyG1AdjustmentWriteback({}, 1200)
    expect(store[G1_ADJ_WRITEBACK_ROW_KEY]?.closingAdjustment).toBe(1200)
  })

  it('分摊到多品种并清零默认行', () => {
    let store = applyG1AdjustmentWriteback({}, 1000)
    const targets = listG1WritebackAllocTargets()
    expect(targets.some((t) => t.rowKey === 'cost-trading-debt')).toBe(true)
    store = allocateG1WritebackAcrossRows(store, 1000, [
      { rowKey: 'cost-trading-debt', amount: 600 },
      { rowKey: 'cost-trading-equity', amount: 400 },
    ])
    expect(store['cost-trading-debt']?.closingAdjustment).toBe(600)
    expect(store['cost-trading-equity']?.closingAdjustment).toBe(400)
    expect(store[G1_ADJ_WRITEBACK_ROW_KEY]?.closingAdjustment).toBe(0)
  })

  it('分摊不足时余数留在默认行', () => {
    let store = applyG1AdjustmentWriteback({}, 1000)
    store = allocateG1WritebackAcrossRows(store, 1000, [
      { rowKey: 'cost-trading-debt', amount: 700 },
    ])
    expect(store['cost-trading-debt']?.closingAdjustment).toBe(700)
    expect(store[G1_ADJ_WRITEBACK_ROW_KEY]?.closingAdjustment).toBe(300)
  })
})
