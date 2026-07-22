/**
 * useH1IdleCheck 纯函数单测：净值 / 迹象 / H1-2识别 / 停提 / 结论草稿
 */
import { describe, it, expect } from 'vitest'
import {
  calcIdleNetValue,
  evaluateImpairmentIndication,
  evaluateDepStopAnomaly,
  idleDurationDays,
  planLabel,
  isIdleDetailCandidate,
  inferIdleTypeFromDetail,
  mapDetailRowToIdle,
  draftIdleConclusion,
  type IdleAssetRow,
  type IdleStatistics,
} from '../composables/useH1IdleCheck'

describe('calcIdleNetValue', () => {
  it('净值 = 原值 - 累计折旧 - 减值准备，且不小于 0', () => {
    expect(calcIdleNetValue(1000, 300, 100)).toBe(600)
    expect(calcIdleNetValue(100, 80, 50)).toBe(0)
  })
})

describe('idleDurationDays', () => {
  it('无起始日返回 null', () => {
    expect(idleDurationDays('')).toBeNull()
  })

  it('按日历日计算闲置天数', () => {
    const asOf = new Date('2025-12-31')
    expect(idleDurationDays('2024-12-31', asOf)).toBe(365)
    expect(idleDurationDays('2025-06-30', asOf)).toBe(184)
  })
})

describe('evaluateImpairmentIndication', () => {
  const base = {
    netValue: 100,
    idleStartDate: '2025-06-01',
    disposalSuggestion: 'idle' as string,
    condition: '完好',
    idleReason: '',
  }
  const asOf = new Date('2025-12-31')

  it('净值为 0 → 无迹象', () => {
    expect(evaluateImpairmentIndication({ ...base, netValue: 0 }, asOf)).toBe(false)
  })

  it('计划处置 → 有迹象', () => {
    expect(evaluateImpairmentIndication({ ...base, disposalSuggestion: 'dispose' }, asOf)).toBe(true)
  })

  it('毁损/待报废 → 有迹象', () => {
    expect(evaluateImpairmentIndication({ ...base, condition: '待报废' }, asOf)).toBe(true)
  })

  it('闲置≥1年且无复用计划 → 有迹象', () => {
    expect(
      evaluateImpairmentIndication({ ...base, idleStartDate: '2024-01-01', disposalSuggestion: 'idle' }, asOf),
    ).toBe(true)
  })

  it('短期闲置+转为使用+状况完好 → 无迹象', () => {
    expect(
      evaluateImpairmentIndication(
        { ...base, idleStartDate: '2025-10-01', disposalSuggestion: 'reuse', condition: '完好' },
        asOf,
      ),
    ).toBe(false)
  })

  it('一般闲置（净值>0）默认有迹象', () => {
    expect(evaluateImpairmentIndication({ ...base, condition: '' }, asOf)).toBe(true)
  })
})

describe('planLabel', () => {
  it('映射处置计划文案', () => {
    expect(planLabel('idle')).toBe('继续闲置')
    expect(planLabel('dispose')).toBe('计划处置')
    expect(planLabel('reuse')).toBe('转为使用')
  })
})

describe('isIdleDetailCandidate / mapDetailRowToIdle', () => {
  it('按关键词识别未使用/不需用', () => {
    expect(isIdleDetailCandidate({ name: '机床A', category: '未使用设备', originalCostEnd: 100 })).toBe(true)
    expect(isIdleDetailCandidate({ name: '叉车', remark: '不需用待处置', originalCostEnd: 50 })).toBe(true)
    expect(isIdleDetailCandidate({ name: '在用机床', category: '机器设备', originalCostEnd: 100 })).toBe(false)
    expect(isIdleDetailCandidate({ name: '闲置', originalCostEnd: 0 })).toBe(false)
  })

  it('推断不需用类型并映射金额', () => {
    expect(inferIdleTypeFromDetail({ category: '不需用固定资产' })).toBe('unneeded')
    const row = mapDetailRowToIdle({
      rowId: 'd1',
      name: '闲置注塑机',
      category: '未使用',
      assetNo: 'FA-01',
      originalCostEnd: 1000,
      accDepEnd: 200,
      impairmentEnd: 50,
      accDepProvision: 0,
    }, 1)
    expect(row.netValue).toBe(750)
    expect(row.idleType).toBe('unused')
    expect(row.periodDepProvision).toBe(0)
    expect(row.remark).toContain('来源:H1-2')
  })
})

describe('evaluateDepStopAnomaly', () => {
  const base = (over: Partial<IdleAssetRow> = {}): IdleAssetRow => ({
    rowId: 'r1',
    seq: 1,
    idleType: 'unused',
    category: '',
    name: '闲置设备',
    assetNo: 'A1',
    originalCost: 1000,
    accDep: 200,
    impairmentProvision: 0,
    netValue: 800,
    idleStartDate: '',
    idleEndDate: '',
    condition: '',
    idleReason: '',
    depContinued: '',
    periodDepProvision: 0,
    disposalSuggestion: 'idle',
    hasImpairment: 'N',
    impairmentAmount: 0,
    remark: '',
    ...over,
  })

  it('明确停提且未提足 → error', () => {
    const w = evaluateDepStopAnomaly(base({ depContinued: 'N' }))
    expect(w?.level).toBe('error')
  })

  it('本期计提为0且未确认继续折旧 → warning', () => {
    const w = evaluateDepStopAnomaly(base({ periodDepProvision: 0, depContinued: '' }))
    expect(w?.level).toBe('warning')
  })

  it('已提足或已确认继续折旧 → 无异常', () => {
    expect(evaluateDepStopAnomaly(base({ netValue: 10, accDep: 990 }))).toBeNull()
    expect(evaluateDepStopAnomaly(base({ depContinued: 'Y', periodDepProvision: 0 }))).toBeNull()
  })
})

describe('draftIdleConclusion', () => {
  it('无闲置时给出空清单表述', () => {
    const stats: IdleStatistics = {
      totalCount: 0,
      unusedCount: 0,
      unneededCount: 0,
      totalOriginalCost: 0,
      totalNetValue: 0,
      impairedTotal: 0,
      indicationCount: 0,
      indicationNotImpairedCount: 0,
      depStopAnomalyCount: 0,
    }
    expect(draftIdleConclusion({ stats, warnings: [], rows: [] })).toContain('未发现')
  })
})
