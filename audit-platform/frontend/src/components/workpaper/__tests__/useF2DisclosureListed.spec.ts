/**
 * useF2DisclosureListed — 对齐 Excel 上市披露模板
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useF2DisclosureListed,
  safeRatio,
  F2_LISTED_DISCLOSURE_CATEGORIES,
} from '../composables/useF2DisclosureListed'
import { buildF2ListedSubTableData } from '../composables/f2DisclosureSyncPayload'
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

describe('safeRatio', () => {
  it('分母为 0 时返回 0（避免 #DIV/0!）', () => {
    expect(safeRatio(10, 0)).toBe(0)
    expect(safeRatio(0, 0)).toBe(0)
  })
  it('正常比例', () => {
    expect(safeRatio(25, 100)).toBe(0.25)
  })
})

describe('useF2DisclosureListed', () => {
  it('分类行对齐 Excel：含在产品/数据资源等 9 类', () => {
    expect(F2_LISTED_DISCLOSURE_CATEGORIES.map((c) => c.label)).toEqual([
      '原材料', '在产品', '委托加工物资', '库存商品', '发出商品',
      '周转材料', '合同履约成本', '消耗性生物资产', '数据资源',
    ])
  })

  it('（1）账面价值=账面余额−跌价；原材料合并在途', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'raw-materials', { opening: 100, increase: 20, decrease: 10, adjustment: 0 })
    setAdj(map, 'gross', 'material-in-transit', { opening: 50, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'raw-materials', { opening: 10, increase: 5, decrease: 2, adjustment: 0 })
    setAdj(map, 'impairment', 'material-in-transit', { opening: 5, increase: 0, decrease: 0, adjustment: 0 })

    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    const raw = api.section1Rows.value.find((r) => r.rowKey === 'raw-materials')!
    expect(raw.priorGross).toBe(150)
    expect(raw.priorImpairment).toBe(15)
    expect(raw.priorNet).toBe(135)
    // endGross = 150 + 20 - 10 = 160; endI = 15 + 5 - 2 = 18
    expect(raw.endGross).toBe(160)
    expect(raw.endImpairment).toBe(18)
    expect(raw.endNet).toBe(142)
  })

  it('（2）期末=期初+计提+其他−转回−其他，并与（1）勾稽', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'finished-goods', { opening: 0, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'finished-goods', {
      opening: 100, increase: 30, decrease: 10, adjustment: 0,
    })

    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    const row = api.section2Rows.value.find((r) => r.rowKey === 'finished-goods')!
    expect(row.opening).toBe(100)
    expect(row.incProvision).toBe(30)
    expect(row.decReversal).toBe(10)
    expect(row.ending).toBe(120)
    expect(Math.abs(row.tieDiff)).toBeLessThan(0.01)

    const cls = api.section1Rows.value.find((r) => r.rowKey === 'finished-goods')!
    expect(cls.endImpairment).toBe(120)
  })

  it('组合比例合计为 0 时显示 0 而非 Infinity', () => {
    const api = useF2DisclosureListed({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
      applicableStandards: ref([]),
    })
    expect(api.s3EndTotal.value.balancePct).toBe(0)
    expect(api.s3EndTotal.value.impairmentPct).toBe(0)
  })

  it('getSyncSnapshot 可构建附注 sync payload', () => {
    const map = new Map<string, ChecklistResponse>()
    setAdj(map, 'gross', 'raw-materials', { opening: 100, increase: 0, decrease: 0, adjustment: 0 })
    setAdj(map, 'impairment', 'raw-materials', { opening: 10, increase: 0, decrease: 0, adjustment: 0 })

    const api = useF2DisclosureListed({
      allResponses: ref(map),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    const sub = buildF2ListedSubTableData(api.getSyncSnapshot())
    expect(sub['存货分类'].length).toBeGreaterThan(1)
    expect(sub['存货分类'][0].label).toBe('原材料')
    expect(sub['存货分类'][0].end_gross).toBe(100)
    expect(sub['存货跌价准备及合同履约成本减值准备'][0].ending).toBe(10)
  })
})
