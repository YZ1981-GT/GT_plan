/**
 * g4AdjudicationItems — applyG4SplitAdjustmentWriteback 测试
 */
import { describe, it, expect } from 'vitest'
import {
  applyG4SplitAdjustmentWriteback,
  parseG4AdjStore,
} from '../g4AdjudicationItems'

describe('applyG4SplitAdjustmentWriteback', () => {
  it('分别回写原值与减值准备行', () => {
    const store = parseG4AdjStore(JSON.stringify({
      'original-portfolio': { closingUnadjusted: 1000, closingAdjustment: 0 },
      'impairment-portfolio': { closingUnadjusted: 50, closingAdjustment: 0 },
    }))
    const next = applyG4SplitAdjustmentWriteback(store, 200, 80)
    expect(next['original-portfolio'].closingAdjustment).toBe(200)
    expect(next['impairment-portfolio'].closingAdjustment).toBe(80)
    expect(String(next['original-portfolio'].reasonAnalysis)).toContain('G4-3')
  })
})
