/**
 * useF2DetailSummary — F2-2 对齐 Excel 三区块
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF2DetailSummary, F2_SUMMARY_CATEGORIES } from '../useF2DetailSummary'
import type { ChecklistResponse } from '../useF2FormData'

describe('useF2DetailSummary', () => {
  it('分类行对齐 Excel（含在产品/数据资源）', () => {
    expect(F2_SUMMARY_CATEGORIES.map((c) => c.label)).toContain('原材料')
    expect(F2_SUMMARY_CATEGORIES.map((c) => c.label)).toContain('在产品')
    expect(F2_SUMMARY_CATEGORIES.map((c) => c.label)).toContain('数据资源')
    expect(F2_SUMMARY_CATEGORIES.some((c) => c.sheetCode === 'F2-3')).toBe(true)
  })

  it('原值未审自明细跨表聚合；审定=未审+调整', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-3-rows', {
      item_id: 'F2-3-rows',
      conclusion: null,
      remark: JSON.stringify([
        { openingAmt: 100, increaseAmt: 50, decreaseAmt: 20, closingAmt: 130 },
        { openingAmt: 40, increaseAmt: 10, decreaseAmt: 5, closingAmt: 45 },
      ]),
    })

    const api = useF2DetailSummary({
      allResponses: ref(map),
      isReadonly: ref(false),
    })

    const raw = api.grossRows.value.find((r) => r.rowKey === 'raw-materials')!
    expect(raw.unaudOpen).toBe(140)
    expect(raw.unaudInc).toBe(60)
    expect(raw.unaudDec).toBe(25)
    expect(raw.unaudClose).toBe(175)
    expect(raw.crossSheet).toBe(true)

    api.updateGrossAdj('raw-materials', 'openingAdj', 10)
    api.updateGrossAdj('raw-materials', 'closeAdjInc', 5)
    const after = api.grossRows.value.find((r) => r.rowKey === 'raw-materials')!
    expect(after.audOpen).toBe(150)
    expect(after.audInc).toBe(65)
    expect(after.audClose).toBe(150 + 65 - 25)
  })

  it('账面价值=原值−跌价；变动率可计算', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-3-rows', {
      item_id: 'F2-3-rows',
      conclusion: null,
      remark: JSON.stringify([
        { openingAmt: 200, increaseAmt: 0, decreaseAmt: 0, closingAmt: 200 },
      ]),
    })
    map.set('F2-1-impairment-raw-materials-opening', {
      item_id: 'F2-1-impairment-raw-materials-opening',
      conclusion: '20',
      remark: null,
    })
    map.set('F2-1-impairment-raw-materials-increase', {
      item_id: 'F2-1-impairment-raw-materials-increase',
      conclusion: '0',
      remark: null,
    })
    map.set('F2-1-impairment-raw-materials-decrease', {
      item_id: 'F2-1-impairment-raw-materials-decrease',
      conclusion: '0',
      remark: null,
    })
    map.set('F2-1-impairment-raw-materials-adjustment', {
      item_id: 'F2-1-impairment-raw-materials-adjustment',
      conclusion: '0',
      remark: null,
    })

    const api = useF2DetailSummary({
      allResponses: ref(map),
      isReadonly: ref(false),
    })

    const bv = api.bvRows.value.find((r) => r.rowKey === 'raw-materials')!
    expect(bv.unaudOpen).toBe(180)
    expect(bv.unaudClose).toBe(180)
    expect(bv.changeRateUnaud).toBe(0)
  })
})
