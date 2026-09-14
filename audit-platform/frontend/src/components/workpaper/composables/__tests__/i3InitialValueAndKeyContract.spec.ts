/**
 * i3InitialValueModel + I3-1 存储键契约
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI3InitialValueRow,
  calcI34Share,
  calcI34Goodwill,
  normalizeI3InitialValueRow,
  buildI34GateWarnings,
  toI34CrossSheetPayload,
} from '../i3InitialValueModel'
import {
  I3_ADJ_ROWS_KEY,
  I3_ADJ_ROWS_KEY_LEGACY,
  I3_ADJ_ROWS_CANDIDATES,
} from '../i3AdjudicationModel'
import { buildI3ConsistencyDashboard } from '../i3ConsistencyModel'

describe('i3InitialValueModel', () => {
  it('非同一控制：⑤=合并成本−应占公允份额', () => {
    const row = emptyI3InitialValueRow({
      sameControl: '否',
      mergerCost: 1000,
      netAssetFV: 800,
      equityRatio: 80,
    })
    expect(calcI34Share(row)).toBeCloseTo(640, 5)
    expect(calcI34Goodwill(row)).toBeCloseTo(360, 5)
  })

  it('同一控制强制商誉为 0', () => {
    const row = emptyI3InitialValueRow({
      sameControl: '是',
      mergerCost: 1000,
      netAssetFV: 800,
      equityRatio: 100,
      bookedAmount: 100,
    })
    expect(calcI34Goodwill(row)).toBe(0)
    expect(buildI34GateWarnings([row]).some((w) => w.includes('同一控制'))).toBe(true)
  })

  it('股权比例兼容 0.7 小数口径', () => {
    const row = normalizeI3InitialValueRow({
      projectName: '甲',
      equityRatio: 0.7,
      mergerCost: 100,
      netAssetFV: 100,
      sameControl: '否',
    })
    expect(row.equityRatio).toBeCloseTo(70, 5)
    expect(calcI34Share(row)).toBeCloseTo(70, 5)
  })

  it('跨表载荷含 goodwillAmount', () => {
    const rows = [emptyI3InitialValueRow({
      projectName: '乙',
      mergerCost: 500,
      netAssetFV: 400,
      equityRatio: 100,
      bookedAmount: 100,
    })]
    const payload = toI34CrossSheetPayload(rows)
    expect(payload[0].investee).toBe('乙')
    expect(payload[0].goodwillAmount).toBe(100)
  })
})

describe('I3-1 storage key contract', () => {
  it('主存键为 I3-adj-rows，并兼容旧键', () => {
    expect(I3_ADJ_ROWS_KEY).toBe('I3-adj-rows')
    expect(I3_ADJ_ROWS_KEY_LEGACY).toBe('I3-1-adj-rows')
    expect([...I3_ADJ_ROWS_CANDIDATES]).toContain('I3-adj-rows')
    expect([...I3_ADJ_ROWS_CANDIDATES]).toContain('I3-1-adj-rows')
  })

  it('一致性仪表盘可读旧键 I3-1-adj-rows', () => {
    const map = new Map<string, any>()
    map.set('I3-2-rows', { remark: JSON.stringify([{ investee: 'A' }]) })
    map.set('I3-1-adj-rows', {
      remark: JSON.stringify([{
        investee: 'A',
        endBalance: 100,
        netValue: 100,
        initialRecognition: 100,
        accImpairment: 0,
      }]),
    })
    const dash = buildI3ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i31-empty')).toBe(false)
  })

  it('I3-6 有数据无 I3-7 时告警', () => {
    const map = new Map<string, any>()
    map.set('I3-2-rows', { remark: JSON.stringify([{ investee: 'A' }]) })
    map.set('I3-6-rows', { remark: JSON.stringify([{ cguName: 'CGU-A' }]) })
    const dash = buildI3ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i37-empty')).toBe(true)
  })
})
