/**
 * F2-10 开发产品 — 原值/跌价/净值公式
 */
import { describe, it, expect } from 'vitest'
import {
  enrichRow,
  normalizeDevProductRow,
  sumDevProductMovement,
  type DevProductRow,
} from '../useF2DevProductSheet'

function row(partial: Partial<DevProductRow> & { id?: string }): DevProductRow {
  return normalizeDevProductRow({ id: '1', ...partial })
}

describe('useF2DevProductSheet enrichRow', () => {
  it('期末 = 期初 + 增加 − 减少；审定 = 账面 + 调整；净值 = 原值 − 跌价', () => {
    const e = enrichRow(row({
      openArea: 100,
      openAmt: 1000,
      openAdjAcct: 50,
      openAdjReclass: -20,
      incArea: 20,
      incAmt: 200,
      decArea: 10,
      decAmt: 100,
      closeAdjAcct: 10,
      closeAdjReclass: 0,
      impOpen: 80,
      impInc: 20,
      impDec: 5,
      impOpenAdjAcct: 5,
    }))
    expect(e.closeArea).toBe(110)
    expect(e.closeAmt).toBe(1100)
    expect(e.openAudAmt).toBe(1030)
    expect(e.closeAudAmt).toBe(1110)
    expect(e.impClose).toBe(95)
    expect(e.impOpenAud).toBe(85)
    expect(e.impCloseAud).toBe(100)
    expect(e.netCloseBookAmt).toBe(1005)
    expect(e.netCloseAudAmt).toBe(1010)
  })

  it('旧版土地/建安数据可迁移为原值收发存', () => {
    const n = normalizeDevProductRow({
      id: 'x',
      projectName: 'A',
      landOpen: 1000,
      buildOpen: 500,
      intOpen: 80,
      otherOpen: 20,
      landIn: 100,
      buildIn: 0,
      intIn: 0,
      otherIn: 0,
      landOut: 50,
      buildOut: 0,
      intOut: 0,
      otherOut: 0,
      transferOut: 30,
    } as any)
    expect(n.openAmt).toBe(1600)
    expect(n.incAmt).toBe(100)
    expect(n.decAmt).toBe(80)
    const e = enrichRow(n)
    expect(e.closeAmt).toBe(1620)
  })

  it('sumDevProductMovement 汇总跨表', () => {
    const mv = sumDevProductMovement([
      { openAmt: 100, incAmt: 50, decAmt: 20 },
      { openAmt: 200, incAmt: 0, decAmt: 10 },
    ])
    expect(mv.opening).toBe(300)
    expect(mv.increase).toBe(50)
    expect(mv.decrease).toBe(30)
    expect(mv.closing).toBe(320)
  })

  it('normalize 补齐缺省字段', () => {
    const n = normalizeDevProductRow({ id: 'x', projectName: 'A' })
    expect(n.projectName).toBe('A')
    expect(n.openAmt).toBe(0)
    expect(n.impOpen).toBe(0)
  })
})
