/**
 * useAgingConfig — 单元测试
 *
 * 测试纯逻辑函数：segmentsToBands、createEmptyAgingData、缓存辅助函数
 * Requirements: 3.1, 3.2, 3.4
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  segmentsToBands,
  createEmptyAgingData,
  PRESET_SEGMENTS,
  invalidateAgingConfigCache,
  clearAgingConfigCache,
  type AgingSegment,
  type AgingBand,
} from '../useAgingConfig'

describe('useAgingConfig — segmentsToBands', () => {
  const fiveYearSegments = PRESET_SEGMENTS.FIVE_YEAR

  it('应为 3-period subject (D2) 生成包含 currentField 的 bands', () => {
    const bands = segmentsToBands(fiveYearSegments, 'D2')
    expect(bands).toHaveLength(6)
    expect(bands[0]).toEqual({
      key: 'within1',
      label: '1年以内',
      priorField: 'agingPrior.within1',
      currentField: 'agingCurrent.within1',
      auditedField: 'agingAudited.within1',
    })
    // 所有 bands 都有 currentField
    for (const band of bands) {
      expect(band.currentField).not.toBe('')
    }
  })

  it('应为 2-period subject (D3) 生成 currentField 为空字符串的 bands', () => {
    const threeYearSegments = PRESET_SEGMENTS.THREE_YEAR
    const bands = segmentsToBands(threeYearSegments, 'D3')
    expect(bands).toHaveLength(4)
    expect(bands[0]).toEqual({
      key: 'within1',
      label: '1年以内',
      priorField: 'agingPrior.within1',
      currentField: '',
      auditedField: 'agingAudited.within1',
    })
    for (const band of bands) {
      expect(band.currentField).toBe('')
    }
  })

  it('应为 3-period subject (F1) 生成 currentField（期末未审账龄）', () => {
    const bands = segmentsToBands(fiveYearSegments, 'F1')
    expect(bands).toHaveLength(6)
    for (const band of bands) {
      expect(band.currentField).toBe(`agingCurrent.${band.key}`)
    }
  })

  it('K1/K3/G5 作为 3-period subjects 应包含 currentField', () => {
    for (const subj of ['K1', 'K3', 'G5']) {
      const bands = segmentsToBands(fiveYearSegments, subj)
      for (const band of bands) {
        expect(band.currentField).not.toBe('')
      }
    }
  })

  it('不传 subject 时默认视为 3-period', () => {
    const bands = segmentsToBands(fiveYearSegments)
    for (const band of bands) {
      expect(band.currentField).not.toBe('')
    }
  })

  it('空 segments 返回空 bands', () => {
    const bands = segmentsToBands([], 'D2')
    expect(bands).toEqual([])
  })

  it('自定义段正确生成字段路径', () => {
    const custom: AgingSegment[] = [
      { key: 'seg_a', label: '6个月以内', dayFrom: 0, dayTo: 180 },
      { key: 'seg_b', label: '6个月-1年', dayFrom: 181, dayTo: 365 },
    ]
    const bands = segmentsToBands(custom, 'D2')
    expect(bands[0].priorField).toBe('agingPrior.seg_a')
    expect(bands[0].currentField).toBe('agingCurrent.seg_a')
    expect(bands[0].auditedField).toBe('agingAudited.seg_a')
    expect(bands[1].priorField).toBe('agingPrior.seg_b')
  })
})

describe('useAgingConfig — createEmptyAgingData', () => {
  const threeYearSegments = PRESET_SEGMENTS.THREE_YEAR
  const fiveYearSegments = PRESET_SEGMENTS.FIVE_YEAR

  it('3-period subject 应生成 agingPrior/agingCurrent/agingAudited 三个对象', () => {
    const data = createEmptyAgingData(fiveYearSegments, 'D2')
    expect(data.agingPrior).toBeDefined()
    expect(data.agingCurrent).toBeDefined()
    expect(data.agingAudited).toBeDefined()
    expect(Object.keys(data.agingPrior!)).toHaveLength(6)
    expect(Object.keys(data.agingCurrent!)).toHaveLength(6)
    expect(Object.keys(data.agingAudited!)).toHaveLength(6)
    // 所有值为 0
    for (const val of Object.values(data.agingPrior!)) {
      expect(val).toBe(0)
    }
  })

  it('2-period subject 应只生成 agingPrior/agingAudited', () => {
    const data = createEmptyAgingData(threeYearSegments, 'D3')
    expect(data.agingPrior).toBeDefined()
    expect(data.agingAudited).toBeDefined()
    expect(data.agingCurrent).toBeUndefined()
    expect(Object.keys(data.agingPrior!)).toHaveLength(4)
  })

  it('F1 作为 3-period 含 agingCurrent（对齐 Excel 期末未审账龄）', () => {
    const data = createEmptyAgingData(fiveYearSegments, 'F1')
    expect(data.agingCurrent).toBeDefined()
    expect(Object.keys(data.agingPrior!)).toHaveLength(6)
    expect(Object.keys(data.agingCurrent!)).toHaveLength(6)
  })

  it('空 segments 生成空对象', () => {
    const data = createEmptyAgingData([], 'D2')
    expect(Object.keys(data.agingPrior!)).toHaveLength(0)
    expect(Object.keys(data.agingCurrent!)).toHaveLength(0)
    expect(Object.keys(data.agingAudited!)).toHaveLength(0)
  })

  it('段 key 与 segments 对应', () => {
    const data = createEmptyAgingData(threeYearSegments, 'K1')
    expect(Object.keys(data.agingPrior!)).toEqual(['within1', 'y1to2', 'y2to3', 'over3'])
  })
})

describe('useAgingConfig — PRESET_SEGMENTS', () => {
  it('THREE_YEAR 预设有 4 个段', () => {
    expect(PRESET_SEGMENTS.THREE_YEAR).toHaveLength(4)
  })

  it('FIVE_YEAR 预设有 6 个段', () => {
    expect(PRESET_SEGMENTS.FIVE_YEAR).toHaveLength(6)
  })

  it('段 dayFrom 单调递增', () => {
    for (const presetName of ['THREE_YEAR', 'FIVE_YEAR']) {
      const segs = PRESET_SEGMENTS[presetName]
      for (let i = 1; i < segs.length; i++) {
        expect(segs[i].dayFrom).toBeGreaterThan(segs[i - 1].dayFrom)
      }
    }
  })

  it('最后一段 dayTo 为 null（无上限）', () => {
    expect(PRESET_SEGMENTS.THREE_YEAR[3].dayTo).toBeNull()
    expect(PRESET_SEGMENTS.FIVE_YEAR[5].dayTo).toBeNull()
  })
})

describe('useAgingConfig — 缓存辅助函数', () => {
  beforeEach(() => {
    clearAgingConfigCache()
  })

  it('invalidateAgingConfigCache 不抛错', () => {
    expect(() => invalidateAgingConfigCache('nonexistent')).not.toThrow()
  })

  it('clearAgingConfigCache 不抛错', () => {
    expect(() => clearAgingConfigCache()).not.toThrow()
  })
})
