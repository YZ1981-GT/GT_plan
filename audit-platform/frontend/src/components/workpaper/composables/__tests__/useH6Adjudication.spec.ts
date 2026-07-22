/**
 * useH6Adjudication — 对齐 Excel H6-1 列结构与公式
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  useH6Adjudication,
  normalizeH61Row,
  buildSignificantFluctuationNote,
  mapH62RowToAdjudication,
  summarizeH11NetValue,
  CHANGE_RATE_THRESHOLD,
} from '../useH6Adjudication'
import { calcH6ChangeRate } from '../useH6FormulaEngine'

function makeMap(entries: Record<string, any> = {}) {
  const map = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    map.set(k, {
      item_id: k,
      remark: typeof v === 'string' ? v : JSON.stringify(v),
      conclusion: null,
    })
  }
  return ref(map)
}

describe('calcH6ChangeRate', () => {
  it('对齐 Excel：期初=0 且变动=0 → 0', () => {
    expect(calcH6ChangeRate(0, 0)).toBe(0)
  })
  it('对齐 Excel：期初=0 且变动>0 → 100%', () => {
    expect(calcH6ChangeRate(100, 0)).toBe(100)
  })
  it('期初=0 且变动<0 → -100%', () => {
    expect(calcH6ChangeRate(-50, 0)).toBe(-100)
  })
  it('正常变动率', () => {
    expect(calcH6ChangeRate(30, 100)).toBe(30)
  })
})

describe('normalizeH61Row', () => {
  it('新格式直接规范化', () => {
    const row = normalizeH61Row({
      name: '设备A',
      beginUnadjusted: 100,
      beginAdjustment: 10,
      endUnadjusted: 80,
      endAdjustment: -5,
    })
    expect(row?.beginAudited).toBe(110)
    expect(row?.endAudited).toBe(75)
    expect(row?.auditedChange).toBe(-35)
  })

  it('旧期末余额行迁移', () => {
    const row = normalizeH61Row({
      name: '期末余额',
      category: 'balance',
      unadjusted: 200,
      aje: 20,
      rje: 5,
      beginBalance: 50,
    })
    expect(row?.name).toBe('固定资产清理')
    expect(row?.endAudited).toBe(225)
    expect(row?.beginAudited).toBe(50)
  })

  it('跳过旧收入/支出行', () => {
    expect(normalizeH61Row({ name: '清理收入', category: 'income', unadjusted: 1 })).toBeNull()
  })
})

describe('mapH62RowToAdjudication', () => {
  it('清理中：期末未审=净值', () => {
    const row = mapH62RowToAdjudication({
      rowId: 'd1',
      assetName: '叉车',
      netBookValue: 1200,
      status: '清理中',
    })
    expect(row.name).toBe('叉车')
    expect(row.endUnadjusted).toBe(1200)
    expect(row.endAudited).toBe(1200)
  })

  it('已结转：期末清零', () => {
    const row = mapH62RowToAdjudication({
      assetName: '机床',
      netBookValue: 0,
      status: '已结转',
    })
    expect(row.endAudited).toBe(0)
  })

  it('优先使用余额变动列', () => {
    const row = mapH62RowToAdjudication({
      assetName: '厂房',
      netBookValue: 999,
      status: '清理中',
      beginUnadjusted: 200,
      beginAdjustment: 20,
      endUnadjusted: 150,
      endAdjustment: -10,
    })
    expect(row.beginAudited).toBe(220)
    expect(row.endAudited).toBe(140)
  })
})

describe('summarizeH11NetValue', () => {
  it('净值=原值−折旧−减值', () => {
    const r = summarizeH11NetValue({
      costRows: [{ beginBalance: 100, audited: 110 }],
      depRows: [{ beginBalance: 30, audited: 40 }],
      impairRows: [{ beginBalance: 5, audited: 5 }],
    })
    expect(r.beginAudited).toBe(65)
    expect(r.endAudited).toBe(65)
  })
})

describe('useH6Adjudication', () => {
  it('合计与变动率≥30% 标红', () => {
    const allResponses = makeMap({
      'H6-1-rows': [
        { name: 'A', beginUnadjusted: 100, beginAdjustment: 0, endUnadjusted: 150, endAdjustment: 0 },
        { name: 'B', beginUnadjusted: 200, beginAdjustment: 0, endUnadjusted: 210, endAdjustment: 0 },
      ],
    })
    const api = useH6Adjudication({
      wpId: ref('w'),
      projectId: ref('p'),
      allResponses,
    })
    expect(api.totalRow.value.endAudited).toBe(360)
    expect(api.totalRow.value.beginAudited).toBe(300)
    expect(api.significantChangeItems.value.map((i) => i.name)).toEqual(['A'])
    expect(CHANGE_RATE_THRESHOLD).toBe(30)
  })

  it('报表核对：清理审定自动带入，差异公式', () => {
    const allResponses = makeMap({
      'H6-1-rows': [
        { name: '清理项', beginUnadjusted: 10, endUnadjusted: 0, beginAdjustment: 0, endAdjustment: 0 },
      ],
    })
    const onSave = vi.fn()
    const api = useH6Adjudication({
      wpId: ref('w'),
      projectId: ref('p'),
      allResponses,
      onSave,
    })
    api.updateFsField('faNetEndAudited', 1000)
    api.updateFsField('faNetBeginAudited', 800)
    api.updateFsField('fsEndAmount', 1000)
    api.updateFsField('fsBeginAmount', 810)

    const rows = api.fsCompareRows.value
    expect(rows.find((r) => r.kind === 'clearing')?.endAudited).toBe(0)
    expect(rows.find((r) => r.kind === 'combined')?.endAudited).toBe(1000)
    expect(rows.find((r) => r.kind === 'diff')?.endAudited).toBe(0)
    expect(rows.find((r) => r.kind === 'diff')?.beginAudited).toBe(0) // 800+10-810=0
  })

  it('从 H6-2 回填完整余额列（期初/账项/期末）', () => {
    const allResponses = makeMap({
      'H6-2-rows': [
        {
          rowId: 'd1',
          assetName: '旧设备',
          netBookValue: 500,
          status: '清理中',
          beginUnadjusted: 100,
          periodIncrease: 400,
          periodDecrease: 0,
          beginAdjustment: 10,
          ajeIncrease: 5,
          ajeDecrease: 0,
          endUnadjusted: 500,
          endAdjustment: 15,
        },
      ],
    })
    const onSave = vi.fn()
    const api = useH6Adjudication({
      wpId: ref('w'),
      projectId: ref('p'),
      allResponses,
      onSave,
    })
    const r = api.syncFromH62('overwrite')
    expect(r.applied).toBe(true)
    expect(api.detailRows.value[0].beginUnadjusted).toBe(100)
    expect(api.detailRows.value[0].beginAdjustment).toBe(10)
    expect(api.detailRows.value[0].beginAudited).toBe(110)
    expect(api.detailRows.value[0].endUnadjusted).toBe(500)
    expect(api.detailRows.value[0].endAdjustment).toBe(15)
    expect(api.detailRows.value[0].endAudited).toBe(515)
  })

  it('从 H1-1 带入固定资产净值', () => {
    const allResponses = makeMap({})
    const onSave = vi.fn()
    const api = useH6Adjudication({
      wpId: ref('w'),
      projectId: ref('p'),
      allResponses,
      onSave,
    })
    const r = api.seedFaNetFromH11({
      costRows: [
        { category: '房屋', beginBalance: 1000, audited: 1200 },
      ],
      depRows: [
        { category: '房屋', beginBalance: 200, audited: 250 },
      ],
      impairRows: [
        { category: '房屋', beginBalance: 0, audited: 50 },
      ],
    })
    expect(r.applied).toBe(true)
    expect(r.beginAudited).toBe(800)
    expect(r.endAudited).toBe(900)
    expect(api.fsReconcile.value.faNetBeginAudited).toBe(800)
    expect(api.fsReconcile.value.faNetEndAudited).toBe(900)
  })

  it('H6-3 账项净额按权重分摊到期末调整', () => {
    const allResponses = makeMap({
      'H6-1-rows': [
        { name: 'A', beginUnadjusted: 0, endUnadjusted: 100, beginAdjustment: 0, endAdjustment: 0 },
        { name: 'B', beginUnadjusted: 0, endUnadjusted: 300, beginAdjustment: 0, endAdjustment: 0 },
      ],
    })
    const onSave = vi.fn()
    const api = useH6Adjudication({
      wpId: ref('w'),
      projectId: ref('p'),
      allResponses,
      onSave,
    })
    api.syncAjeRjeFromAdjustment(40, 0)
    expect(api.detailRows.value[0].endAdjustment).toBe(10)
    expect(api.detailRows.value[1].endAdjustment).toBe(30)
    expect(api.endBalanceAudited.value).toBe(440)
  })
})

describe('buildSignificantFluctuationNote', () => {
  it('生成说明草稿', () => {
    const note = buildSignificantFluctuationNote([
      { name: '设备A', beginAudited: 100, endAudited: 150, auditedChange: 50, auditedChangeRate: 50 },
    ])
    expect(note).toContain('设备A')
    expect(note).toContain('30%')
  })
})
