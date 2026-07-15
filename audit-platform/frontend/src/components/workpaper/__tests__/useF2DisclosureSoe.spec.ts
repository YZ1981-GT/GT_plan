/**
 * useF2DisclosureSoe — 国企附注披露口径（对照 Excel）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF2DisclosureSoe } from '../composables/useF2DisclosureSoe'
import type { ChecklistResponse } from '../composables/useF2FormData'

function setAdj(
  map: Map<string, ChecklistResponse>,
  block: 'gross' | 'impairment',
  rowKey: string,
  fields: Record<string, number>,
) {
  for (const [field, val] of Object.entries(fields)) {
    map.set(`F2-1-${block}-${rowKey}-${field}`, {
      item_id: `F2-1-${block}-${rowKey}-${field}`,
      conclusion: String(val),
      remark: null,
    })
  }
}

describe('useF2DisclosureSoe', () => {
  it('未配置准则时仍适用（与上市附注一致）', () => {
    const api = useF2DisclosureSoe({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
      applicableStandards: ref([]),
    })
    expect(api.isApplicable.value).toBe(true)
    expect(api.section1Rows.value.length).toBeGreaterThan(0)
  })

  it('（1）合并原材料=材料+在途，合计扣「其中」防双计', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'raw-materials', { opening: 100, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'gross', 'material-in-transit', { opening: 50, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'raw-materials', { opening: 10, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'material-in-transit', { opening: 5, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'gross', 'dev-costs', { opening: 200, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'dev-costs', { opening: 20, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'gross', 'work-in-progress', { opening: 80, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'work-in-progress', { opening: 0, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'gross', 'semi-finished', { opening: 20, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'semi-finished', { opening: 0, increase: 0, decrease: 0, adjustment: 0 })

    const api = useF2DisclosureSoe({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['soe']),
    })

    expect(api.isApplicable.value).toBe(true)
    const raw = api.section1Rows.value.find((r) => r.rowKey === 'raw-combined')!
    expect(raw.priorGross).toBe(150)
    expect(raw.priorImpairment).toBe(15)
    expect(raw.priorNet).toBe(135)

    const wip = api.section1Rows.value.find((r) => r.rowKey === 'wip-combined')!
    expect(wip.priorGross).toBe(300) // 80+20+200
    const detail = api.section1Rows.value.find((r) => r.rowKey === 'dev-costs')!
    expect(detail.priorGross).toBe(200)

    // 合计不含「其中」：raw 150 + wip 300 = 450，不含再加一遍 200
    expect(api.section1Total.value.priorGross).toBe(450)
  })

  it('（2）跌价期末=期初+计提+其他−转回−转销−其他，并与(1)勾稽', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'finished-goods', { opening: 0, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'finished-goods', {
      opening: 100, increase: 30, decrease: 10, adjustment: 0,
    })

    const api = useF2DisclosureSoe({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['state_owned']),
    })

    const row = api.section2Rows.value.find((r) => r.rowKey === 'fg-combined')!
    expect(row.opening).toBe(100)
    expect(row.incProvision).toBe(30)
    expect(row.decReversal).toBe(10)
    expect(row.ending).toBe(120)
    expect(Math.abs(row.tieDiff)).toBeLessThan(0.01)
  })
})
