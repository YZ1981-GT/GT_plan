/**
 * useH6Detail — 挂账警告 / 减值净值 单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  useH6Detail,
  getDetailRowWarnings,
} from '../composables/useH6Detail'

function makeAllResponses(entries: Record<string, any> = {}) {
  const map = new Map<string, any>()
  for (const [key, val] of Object.entries(entries)) {
    map.set(key, { item_id: key, conclusion: null, remark: String(val) })
  }
  return ref(map)
}

describe('getDetailRowWarnings', () => {
  const asOf = '2025-12-31'

  it('已结转且净损益≠0 不告警（净损益结转属正常）', () => {
    const ws = getDetailRowWarnings({
      status: '已结转',
      startDate: '2025-06-01',
      overOneYearProgress: '',
      transferAccount: '资产处置损益',
    }, asOf)
    expect(ws).toHaveLength(0)
  })

  it('超1年未结转且无进展 → over_one_year_no_progress', () => {
    const ws = getDetailRowWarnings({
      status: '清理中',
      startDate: '2023-01-01',
      overOneYearProgress: '',
      transferAccount: '',
    }, asOf)
    expect(ws.some(w => w.kind === 'over_one_year_no_progress')).toBe(true)
    expect(ws.some(w => w.kind === 'uncleared')).toBe(true)
  })

  it('超1年但已填进展 → 无 over_one_year 警告', () => {
    const ws = getDetailRowWarnings({
      status: '清理中',
      startDate: '2023-01-01',
      overOneYearProgress: '诉讼未结，预计次年结转',
      transferAccount: '',
    }, asOf)
    expect(ws.some(w => w.kind === 'over_one_year_no_progress')).toBe(false)
  })

  it('已结转但未填结转科目 → transferred_missing_account', () => {
    const ws = getDetailRowWarnings({
      status: '已结转',
      startDate: '2025-01-01',
      overOneYearProgress: '',
      transferAccount: '',
    }, asOf)
    expect(ws.some(w => w.kind === 'transferred_missing_account')).toBe(true)
  })
})

describe('useH6Detail — 减值与挂账', () => {
  it('余额变动：期末未审=期初+增加−减少；审定列公式', () => {
    const allResponses = makeAllResponses({})
    const onSave = vi.fn()
    const { createFromH1Disposal, rows, updateCell } = useH6Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      onSave,
      periodEndDate: ref('2025-12-31'),
    })

    createFromH1Disposal({
      assetName: '设备A',
      originalCost: 100000,
      accDep: 30000,
      impairment: 10000,
      refH1Code: 'H1-8-1',
      startDate: '2025-03-01',
    })

    expect(rows.value[0].periodIncrease).toBe(60000)
    expect(rows.value[0].endUnadjusted).toBe(60000)
    expect(rows.value[0].beginAudited).toBe(0)
    expect(rows.value[0].endAudited).toBe(60000)

    updateCell(rows.value[0].rowId, 'beginAdjustment', 1000)
    expect(rows.value[0].beginAudited).toBe(1000)
    expect(rows.value[0].endAdjustment).toBe(1000)
    expect(rows.value[0].endAudited).toBe(61000)
  })

  it('旧存档无余额列时按净值推导', () => {
    const allResponses = makeAllResponses({
      'H6-2-rows': JSON.stringify([{
        rowId: 'r1',
        assetName: '旧设备',
        originalCost: 50,
        accumulatedDepreciation: 10,
        status: '清理中',
      }]),
    })
    const { rows } = useH6Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
    })
    expect(rows.value[0].netBookValue).toBe(40)
    expect(rows.value[0].periodIncrease).toBe(40)
    expect(rows.value[0].endUnadjusted).toBe(40)
  })

  it('超1年未结转计入 statusSummary.overOneYearUncleared', () => {
    const allResponses = makeAllResponses({
      'H6-2-rows': JSON.stringify([{
        rowId: 'r1',
        assetName: '旧设备',
        originalCost: 50,
        accumulatedDepreciation: 10,
        startDate: '2022-01-01',
        status: '清理中',
      }]),
    })
    const { statusSummary, hasCriticalWarning } = useH6Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      onSave: vi.fn(),
      periodEndDate: ref('2025-12-31'),
    })

    expect(statusSummary.value.overOneYearUncleared).toBe(1)
    expect(hasCriticalWarning.value).toBe(true)
  })
})
