/**
 * F2-10 开发产品 — 原值/跌价/净值公式与遗留迁移
 */
import { describe, it, expect } from 'vitest'
import {
  enrichRow,
  normalizeDevProductRow,
  type DevProductRow,
} from '../useF2DevProductSheet'

function row( partial: Partial<DevProductRow> & { id?: string }): DevProductRow {
  return normalizeDevProductRow({ id: '1', ...partial })
}

describe('useF2DevProductSheet enrichRow', () => {
  it('原值：期末未审=期初+转入-转出；审定=未审+调整', () => {
    const e = enrichRow(row({
      costOpenArea: 100,
      costOpenAmt: 1000,
      costOpenBookAdj: 50,
      costOpenReclassAdj: -10,
      costInArea: 20,
      costInAmt: 200,
      costOutArea: 10,
      costOutAmt: 100,
      costCloseBookAdj: 5,
      costCloseReclassAdj: 0,
    }))
    expect(e.costOpenAuditedAmt).toBe(1040)
    expect(e.costCloseArea).toBe(110)
    expect(e.costCloseAmt).toBe(1100)
    expect(e.costCloseAuditedAmt).toBe(1105)
  })

  it('跌价：未审滚存 + 调整 → 审定', () => {
    const e = enrichRow(row({
      impOpen: 100,
      impIncrease: 40,
      impDecrease: 10,
      impOpenBookAdj: 5,
      impOpenReclassAdj: 0,
      impBookInc: 2,
      impBookDec: 1,
      impReclassInc: 0,
      impReclassDec: 0,
    }))
    expect(e.impClose).toBe(130)
    expect(e.impAuditedOpen).toBe(105)
    expect(e.impAuditedInc).toBe(42)
    expect(e.impAuditedDec).toBe(11)
    expect(e.impAuditedClose).toBe(136)
  })

  it('净值：原值 − 跌价', () => {
    const e = enrichRow(row({
      costOpenAmt: 1000,
      costInAmt: 0,
      costOutAmt: 0,
      costCloseBookAdj: 0,
      costCloseReclassAdj: 0,
      costOpenArea: 100,
      impOpen: 100,
      impIncrease: 0,
      impDecrease: 0,
    }))
    expect(e.netOpenUnauditedAmt).toBe(900)
    expect(e.netCloseUnauditedAmt).toBe(900)
    expect(e.netOpenAuditedAmt).toBe(900)
    expect(e.netCloseAuditedAmt).toBe(900)
  })

  it('遗留土地/建安壳迁移为原值金额', () => {
    const n = normalizeDevProductRow({
      id: 'x',
      projectName: 'A盘',
      landOpen: 100,
      buildOpen: 200,
      intOpen: 50,
      otherOpen: 10,
      landIn: 1,
      buildIn: 2,
      intIn: 3,
      otherIn: 4,
      landOut: 0,
      buildOut: 0,
      intOut: 0,
      otherOut: 0,
      transferOut: 5,
    })
    expect(n.costOpenAmt).toBe(360)
    expect(n.costInAmt).toBe(10)
    expect(n.costOutAmt).toBe(5)
  })
})
