/**
 * F2-11 开发成本 — 未审/调整/审定与净值公式
 */
import { describe, it, expect } from 'vitest'
import {
  enrichRow,
  normalizeDevCostRow,
  sumDevCostMovement,
  type DevCostRow,
} from '../useF2DevCostSheet'

function row(partial: Partial<DevCostRow> & { id?: string }): DevCostRow {
  return normalizeDevCostRow({ id: '1', ...partial })
}

describe('useF2DevCostSheet enrichRow', () => {
  it('审定增减含账项与重分类；净值 = 原值 − 跌价', () => {
    const e = enrichRow(row({
      unaudOpen: 1000,
      unaudInc: 200,
      unaudDec: 50,
      adjAcctInc: 10,
      adjAcctDec: 5,
      adjReclassInc: 20,
      adjReclassDec: 0,
      impUnaudOpen: 80,
      impUnaudInc: 10,
      impUnaudDec: 0,
      impAdjAcctInc: 5,
    }))
    expect(e.unaudClose).toBe(1150)
    expect(e.audOpen).toBe(1000)
    expect(e.audInc).toBe(230)
    expect(e.audDec).toBe(55)
    expect(e.audClose).toBe(1175)
    expect(e.impUnaudClose).toBe(90)
    expect(e.impAudInc).toBe(15)
    expect(e.impAudClose).toBe(95)
    expect(e.netUnaudClose).toBe(1060)
    expect(e.netAudClose).toBe(1080)
  })

  it('sumDevCostMovement 汇总跨表', () => {
    const mv = sumDevCostMovement([
      { unaudOpen: 100, unaudInc: 50, unaudDec: 20 },
      { unaudOpen: 200, unaudInc: 0, unaudDec: 10 },
    ])
    expect(mv.opening).toBe(300)
    expect(mv.increase).toBe(50)
    expect(mv.decrease).toBe(30)
    expect(mv.closing).toBe(320)
  })
})
