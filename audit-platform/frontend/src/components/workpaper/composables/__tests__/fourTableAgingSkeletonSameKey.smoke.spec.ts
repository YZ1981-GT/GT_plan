/**
 * fourTableAgingSkeletonSameKey.smoke.spec.ts
 *
 * Feature: four-table-extraction-entry-completion (Task 13)
 *
 * 冒烟守卫（最小集，Task 14 拥有合并守卫套件）：验证 Task 13 的两条行为不变式，
 * 落在 K1/D3/D7 明细取数骨架实际使用的公共 seam（useAgingConfig + useAgingMigration）：
 *
 * 1. 同键：取数骨架各账龄段 key 集 === useAgingConfig 当前枚举 bands 的 key 集
 *    （三年 / 五年 / 自定义三种配置均成立）。三处（明细骨架 / 审定表 / 附注）都经
 *    createEmptyAgingData(segments) + segmentsToBands(segments) 派生，故段 key 单一真源。
 * 2. 枚举切换重映射：remapRowAgingData 把已录账龄从旧段搬到新段，重叠段值保留、
 *    新增段零初始化、旧段丢弃 —— 不丢已录数据、不错位。
 *
 * **Validates: Requirements 7.2, 7.4, 7.5**
 */
import { describe, it, expect } from 'vitest'
import {
  PRESET_SEGMENTS,
  segmentsToBands,
  createEmptyAgingData,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import { remapRowAgingData } from '@/composables/useAgingMigration'

const THREE_YEAR = PRESET_SEGMENTS.THREE_YEAR
const FIVE_YEAR = PRESET_SEGMENTS.FIVE_YEAR
const CUSTOM: AgingSegment[] = [
  { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
  { key: 'y1to3', label: '1-3年', dayFrom: 366, dayTo: 1095 },
  { key: 'over3', label: '3年以上', dayFrom: 1096, dayTo: null },
]

function keysOf(obj: Record<string, number>): string[] {
  return Object.keys(obj).sort()
}
function bandKeys(segments: AgingSegment[]): string[] {
  return segmentsToBands(segments).map((b) => b.key).sort()
}

describe('Task 13 — 取数骨架与 useAgingConfig bands 同键（7.2/7.5）', () => {
  for (const [name, segments, subject] of [
    ['三年 / 2-period (D3/D7)', THREE_YEAR, 'D3'],
    ['五年 / 3-period (K1)', FIVE_YEAR, 'K1'],
    ['自定义 / 3-period (K1)', CUSTOM, 'K1'],
  ] as const) {
    it(`${name}：createEmptyAgingData 段键集 === bands 段键集`, () => {
      const skeleton = createEmptyAgingData(segments, subject)
      const expectedKeys = bandKeys(segments)

      // agingPrior / agingAudited 恒存在，键集与 bands 一致
      expect(keysOf(skeleton.agingPrior)).toEqual(expectedKeys)
      expect(keysOf(skeleton.agingAudited)).toEqual(expectedKeys)

      // 3-period subject 有 agingCurrent 且同键；2-period 无
      const isThreePeriod = ['D2', 'K1', 'K3', 'G5', 'F1'].includes(subject)
      if (isThreePeriod) {
        expect(skeleton.agingCurrent).toBeDefined()
        expect(keysOf(skeleton.agingCurrent!)).toEqual(expectedKeys)
      } else {
        expect(skeleton.agingCurrent).toBeUndefined()
      }
    })

    it(`${name}：取数骨架各段值全为 0（不塞首段，Property 5 前端侧）`, () => {
      const skeleton = createEmptyAgingData(segments, subject)
      const allZero = (o?: Record<string, number>) =>
        !o || Object.values(o).every((v) => v === 0)
      expect(allZero(skeleton.agingPrior)).toBe(true)
      expect(allZero(skeleton.agingAudited)).toBe(true)
      expect(allZero(skeleton.agingCurrent)).toBe(true)
    })
  }
})

describe('Task 13 — 枚举切换 remapRowAgingData 不丢/不错位（7.4）', () => {
  it('五年 → 三年：重叠段保留、五年独有段丢弃、无错位', () => {
    // 已录一行五年账龄（3-period）
    const row = {
      id: 'r1',
      counterparty: '甲公司',
      agingPrior: { within1: 10, y1to2: 20, y2to3: 30, y3to4: 40, y4to5: 50, over5: 60 },
      agingCurrent: { within1: 1, y1to2: 2, y2to3: 3, y3to4: 4, y4to5: 5, over5: 6 },
      agingAudited: { within1: 100, y1to2: 200, y2to3: 300, y3to4: 400, y4to5: 500, over5: 600 },
    }
    const remapped = remapRowAgingData(row, THREE_YEAR, true)

    // 新段键集 === 三年 bands
    expect(keysOf(remapped.agingAudited)).toEqual(bandKeys(THREE_YEAR))
    // 重叠段（within1/y1to2/y2to3）值逐段保留、不错位
    expect(remapped.agingAudited.within1).toBe(100)
    expect(remapped.agingAudited.y1to2).toBe(200)
    expect(remapped.agingAudited.y2to3).toBe(300)
    // 三年新增段 over3 无旧值 → 零初始化（五年无 over3 段）
    expect(remapped.agingAudited.over3).toBe(0)
    // 五年独有段（y3to4/y4to5/over5）已丢弃
    expect('y3to4' in remapped.agingAudited).toBe(false)
    expect('over5' in remapped.agingAudited).toBe(false)
    // 非账龄字段保留
    expect(remapped.counterparty).toBe('甲公司')
  })

  it('三年 → 五年：重叠段（within1/y1to2/y2to3）保留、五年新增段零初始化、三年末段 over3 丢弃', () => {
    const row = {
      rowId: 'r2',
      agingPrior: { within1: 5, y1to2: 6, y2to3: 7, over3: 8 },
      agingAudited: { within1: 11, y1to2: 12, y2to3: 13, over3: 14 },
    }
    // D3/D7 为 2-period（isThreePeriod=false）
    const remapped = remapRowAgingData(row, FIVE_YEAR, false)

    expect(keysOf(remapped.agingAudited)).toEqual(bandKeys(FIVE_YEAR))
    expect(remapped.agingAudited.within1).toBe(11)
    expect(remapped.agingAudited.y1to2).toBe(12)
    expect(remapped.agingAudited.y2to3).toBe(13)
    // 五年末段 key 为 over5（非 over3）；三年的 over3 在五年中无同 key 段 → 丢弃
    expect('over3' in remapped.agingAudited).toBe(false)
    // 五年新增段零初始化
    expect(remapped.agingAudited.y3to4).toBe(0)
    expect(remapped.agingAudited.y4to5).toBe(0)
    expect(remapped.agingAudited.over5).toBe(0)
    // 2-period 不应生成 agingCurrent
    expect(remapped.agingCurrent).toBeUndefined()
  })

  it('五年 → 自定义：仅重叠段（within1/over3）保留，其余零初始化', () => {
    const row = {
      agingAudited: { within1: 1, y1to2: 2, y2to3: 3, y3to4: 4, y4to5: 5, over5: 6 },
    }
    const remapped = remapRowAgingData(row, CUSTOM, false)
    expect(keysOf(remapped.agingAudited)).toEqual(bandKeys(CUSTOM))
    expect(remapped.agingAudited.within1).toBe(1) // 重叠段保留
    expect(remapped.agingAudited.y1to3).toBe(0)   // 自定义新增段零初始化
    expect(remapped.agingAudited.over3).toBe(0)   // 五年无 over3 段 → 零初始化
  })
})
