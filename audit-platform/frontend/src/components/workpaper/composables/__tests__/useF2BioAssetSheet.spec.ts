/**
 * F2-13 消耗性生物资产 — 原值/跌价/净值
 */
import { describe, it, expect } from 'vitest'
import {
  enrichRow,
  normalizeBioAssetRow,
  sumBioAssetMovement,
  type BioAssetRow,
} from '../useF2BioAssetSheet'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

const segs = PRESET_SEGMENTS.THREE_YEAR

function row(partial: Partial<BioAssetRow> & { id?: string }): BioAssetRow {
  return normalizeBioAssetRow({ id: '1', ...partial }, segs)
}

describe('useF2BioAssetSheet', () => {
  it('收发存与跌价审定、净值公式', () => {
    const e = enrichRow(row({
      openQty: 10,
      openAmt: 1000,
      incQty: 5,
      incAmt: 400,
      decQty: 2,
      decAmt: 200,
      aging: { within1: 1200, y1to2: 0, y2to3: 0, over3: 0 },
      impOpen: 80,
      impInc: 20,
      impDec: 5,
      impAdjReclass: 10,
      impAdjInc: 5,
      impAdjDec: 0,
    }), segs)
    expect(e.closeQty).toBe(13)
    expect(e.closeAmt).toBe(1200)
    expect(e.agingOk).toBe(true)
    expect(e.impClose).toBe(95)
    expect(e.impAudOpen).toBe(90)
    expect(e.impAudInc).toBe(25)
    expect(e.impAudClose).toBe(110)
    expect(e.netCloseAmt).toBe(1105)
  })

  it('sumBioAssetMovement 汇总', () => {
    const mv = sumBioAssetMovement([
      { openAmt: 100, incAmt: 50, decAmt: 20 },
      { openAmt: 200, incAmt: 0, decAmt: 10 },
    ])
    expect(mv.opening).toBe(300)
    expect(mv.closing).toBe(320)
  })
})
