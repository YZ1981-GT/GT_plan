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
    // 🔴 原 fixture 还给 `work-in-progress` 喂了 80 —— 但审定表没有这个 rowKey
    // （1404 是 `semi-finished`），属伪造键。Sprint 8 已把该死键从 sourceKeys 删除，
    // 这里把金额并回真实键 `semi-finished`，保持「合并取数」的被验证语义（100 + 200 = 300）。
    setAdj(map, 'gross', 'semi-finished', { opening: 100, increase: 0, decrease: 0, adjustment: 0 })
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
    expect(wip.priorGross).toBe(300) // semi-finished 100 + dev-costs 200
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

  // ── (5) 确认为存货的数据资源（R3）──
  describe('（5）确认为存货的数据资源', () => {
    function mountWithDr(remark?: string) {
      const map = new Map<string, ChecklistResponse>()
      if (remark !== undefined) {
        map.set('F2-note-soe-s5-data-resource', {
          item_id: 'F2-note-soe-s5-data-resource',
          conclusion: null,
          remark,
        })
      }
      return useF2DisclosureSoe({
        allResponses: ref(map),
        isReadonly: ref(false),
        applicableStandards: ref(['soe']),
      })
    }

    it('21 行三段式，国企段标题为「二、跌价准备」', () => {
      const api = mountWithDr()
      expect(api.drRows.value).toHaveLength(21)
      expect(api.drRows.value.filter((r) => r.kind === 'section').map((r) => r.label)).toEqual([
        '一、账面原值', '二、跌价准备', '三、账面价值',
      ])
      expect(api.drIsEmpty.value).toBe(true)
    })

    it('录入后期末/账面价值/合计按公式联动', () => {
      const api = mountWithDr(JSON.stringify({
        'gross-open': { purchased: 100, selfProcessed: 50, other: 0 },
        'gross-inc': { purchased: 20, selfProcessed: 0, other: 5 },
        'gross-dec': { purchased: 10, selfProcessed: 0, other: 0 },
        'imp-open': { purchased: 8, selfProcessed: 2, other: 0 },
      }))
      expect(api.drIsEmpty.value).toBe(false)

      const grossEnd = api.drRows.value.find((r) => r.rowKey === 'gross-end')!
      expect(grossEnd.purchased).toBe(110)
      expect(grossEnd.total).toBe(165) // 110 + 50 + 5

      const impEnd = api.drRows.value.find((r) => r.rowKey === 'imp-end')!
      expect(impEnd.total).toBe(10)

      const nvEnd = api.drRows.value.find((r) => r.rowKey === 'nv-end')!
      expect(nvEnd.purchased).toBe(102) // 110 - 8
      const nvOpen = api.drRows.value.find((r) => r.rowKey === 'nv-open')!
      expect(nvOpen.purchased).toBe(92) // 100 - 8
    })

    it('updateDrCell 写入录入行、忽略派生行', () => {
      const api = mountWithDr()
      api.updateDrCell('imp-inc', 'purchased', 42)
      expect(api.drRows.value.find((r) => r.rowKey === 'imp-inc')!.purchased).toBe(42)

      api.updateDrCell('imp-end', 'purchased', 999)
      // imp-end 仍为公式值 0 + 42 - 0
      expect(api.drRows.value.find((r) => r.rowKey === 'imp-end')!.purchased).toBe(42)
    })

    it('remark 非法 JSON 时回退空表而非抛错', () => {
      const api = mountWithDr('{not json')
      expect(api.drRows.value).toHaveLength(21)
      expect(api.drIsEmpty.value).toBe(true)
    })

    it('getSyncSnapshot 携带 21 行数据资源子表', () => {
      const api = mountWithDr(JSON.stringify({ 'gross-open': { purchased: 7 } }))
      const snap = api.getSyncSnapshot()
      expect(snap.s5DataResourceRows).toHaveLength(21)
      expect(snap.s5DataResourceRows[1].purchased).toBe(7)
      expect(snap.s5DataResourceRows[1].total).toBe(7)
    })
  })
})
