/**
 * H1-8 减少检查 — 联动总体 / 报废残值提示 单元测试
 */
import { describe, it, expect } from 'vitest'
import { isScrapMethod } from '../useH1DisposalCheck'
import { calcNetValue, calcDisposalGainLoss } from '../useH1FormulaEngine'

describe('isScrapMethod', () => {
  it('识别报废/损毁中英文', () => {
    expect(isScrapMethod('报废')).toBe(true)
    expect(isScrapMethod('损毁')).toBe(true)
    expect(isScrapMethod('scrap')).toBe(true)
    expect(isScrapMethod('damage')).toBe(true)
    expect(isScrapMethod('出售')).toBe(false)
    expect(isScrapMethod('')).toBe(false)
  })
})

describe('报废无收入残值场景勾稽', () => {
  it('净值>0 且收入=0 时净损益为负（需残值提示）', () => {
    const net = calcNetValue(100_000, 60_000, 0)
    expect(net).toBe(40_000)
    const gl = calcDisposalGainLoss(0, net, 0)
    expect(gl).toBe(-40_000)
  })

  it('有残值收入后净损益改善', () => {
    const net = calcNetValue(100_000, 60_000, 0)
    expect(calcDisposalGainLoss(5_000, net, 500)).toBe(5_000 - 40_000 - 500)
  })
})
