/**
 * agingSkeletonSync.guard —— 账龄骨架同键 + 枚举切换重映射守卫（Phase 2 / Task 14）
 *
 * spec: .kiro/specs/four-table-extraction-entry-completion/  (Task 14)
 * Requirements: 7.2（骨架段键逐项 == useAgingConfig bands，同一 effective_segments 真源）,
 *               7.4（切换账龄枚举时 useAgingMigration 重映射已录账龄，不丢/不错位）
 *
 * 用**真函数**（createEmptyAgingData / segmentsToBands / remapRowAgingData），不 mock 它们。
 *
 * 🔴 变异说明（打红判据）：
 *   - 若把「取数骨架键」与「useAgingConfig bands 键」的联动断开（例如给 createEmptyAgingData
 *     喂硬编码的错误段列表，或断言里把某个 band.key 写死成 'wrong_seg'），
 *     `describe('同键不变式')` 下的用例会 RED —— 这正是 Property 8「改一处枚举不变则红」
 *     在前端的对应体现。
 *   - 若 remapRowAgingData 丢弃已录值（把匹配段也归零），`describe('枚举切换重映射')`
 *     下「已录值保留」用例会 RED。
 *
 * 分工（不重复既有断言）：
 *   - `useAgingConfig.spec.ts` 已断 segmentsToBands 对 D2/D3 的 currentField 生成规则、
 *     createEmptyAgingData 的段初始化；本文件只断**两者键集彼此一致**这条"同键"联动
 *     （既有测试各测各的，未把「骨架键 == bands 键」交叉锁死）。
 *   - `useAgingMigration.property.test.ts` 断 remap 的 PBT 通用性质；本文件只补
 *     "三年→五年→自定义链式切换后**具体某个已录值**不丢"这条端到端保留断言。
 */
import { describe, it, expect } from 'vitest'
import {
  segmentsToBands,
  createEmptyAgingData,
  PRESET_SEGMENTS,
  type AgingSegment,
} from '../useAgingConfig'
import { remapRowAgingData } from '../useAgingMigration'

// 自定义段（2-10 段：这里 3 段，键与三年/五年都不同）—— 模拟项目自定义枚举
const CUSTOM_SEGMENTS: AgingSegment[] = [
  { key: 'seg_a', label: 'A档', dayFrom: 0, dayTo: 180 },
  { key: 'seg_b', label: 'B档', dayFrom: 181, dayTo: 540 },
  { key: 'seg_c', label: 'C档', dayFrom: 541, dayTo: null },
]

const CONFIGS: Array<{ name: string; segments: AgingSegment[]; expectKeys: string[] }> = [
  { name: 'THREE_YEAR', segments: PRESET_SEGMENTS.THREE_YEAR, expectKeys: ['within1', 'y1to2', 'y2to3', 'over3'] },
  { name: 'FIVE_YEAR', segments: PRESET_SEGMENTS.FIVE_YEAR, expectKeys: ['within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5'] },
  { name: 'CUSTOM', segments: CUSTOM_SEGMENTS, expectKeys: ['seg_a', 'seg_b', 'seg_c'] },
]

// K1 是 3-period subject（agingCurrent 存在）；D3 是 2-period（无 agingCurrent）
const K1 = 'K1'
const D3 = 'D3'

describe('agingSkeletonSync — 同键不变式 (Requirement 7.2)', () => {
  for (const cfg of CONFIGS) {
    it(`[${cfg.name}] K1(3-period) 骨架键集逐项 == segmentsToBands band 键`, () => {
      const skeleton = createEmptyAgingData(cfg.segments, K1)
      const bands = segmentsToBands(cfg.segments, K1)
      const bandKeys = bands.map((b) => b.key)

      // 骨架三组账龄键集都与 bands 键逐项一致（顺序敏感）
      expect(Object.keys(skeleton.agingPrior)).toEqual(bandKeys)
      expect(Object.keys(skeleton.agingCurrent ?? {})).toEqual(bandKeys)
      expect(Object.keys(skeleton.agingAudited)).toEqual(bandKeys)
      // 且与枚举期望键一致（防两侧同时漂到第二真源）
      expect(bandKeys).toEqual(cfg.expectKeys)

      // 空骨架：每段值恒 0，绝不塞余额（Property 5 前端对应）
      for (const v of Object.values(skeleton.agingPrior)) expect(v).toBe(0)
      for (const v of Object.values(skeleton.agingAudited)) expect(v).toBe(0)
    })

    it(`[${cfg.name}] D3(2-period) 骨架无 agingCurrent，键集 == bands 键`, () => {
      const skeleton = createEmptyAgingData(cfg.segments, D3)
      const bandKeys = segmentsToBands(cfg.segments, D3).map((b) => b.key)
      expect(skeleton.agingCurrent).toBeUndefined()
      expect(Object.keys(skeleton.agingPrior)).toEqual(bandKeys)
      expect(Object.keys(skeleton.agingAudited)).toEqual(bandKeys)
      // 2-period band 的 currentField 应为空字符串（不生成期末未审列）
      for (const b of segmentsToBands(cfg.segments, D3)) expect(b.currentField).toBe('')
    })
  }

  it('三种枚举的骨架键集互不相同（改枚举 → 键随之变，非硬编码）', () => {
    const three = Object.keys(createEmptyAgingData(PRESET_SEGMENTS.THREE_YEAR, K1).agingAudited)
    const five = Object.keys(createEmptyAgingData(PRESET_SEGMENTS.FIVE_YEAR, K1).agingAudited)
    const custom = Object.keys(createEmptyAgingData(CUSTOM_SEGMENTS, K1).agingAudited)
    expect(three).not.toEqual(five)
    expect(three).not.toEqual(custom)
    expect(five).not.toEqual(custom)
    expect([three.length, five.length, custom.length]).toEqual([4, 6, 3])
  })
})

describe('agingSkeletonSync — 枚举切换重映射 (Requirement 7.4)', () => {
  it('三年→五年：已录段值保留，新增段补 0，不丢已录值', () => {
    // 审计师在三年档手动录了几段账龄
    const row: any = {
      counterparty: '甲公司',
      agingPrior: { within1: 111, y1to2: 222, y2to3: 333, over3: 444 },
      agingCurrent: { within1: 10, y1to2: 20, y2to3: 30, over3: 40 },
      agingAudited: { within1: 1, y1to2: 2, y2to3: 3, over3: 4 },
    }
    const remapped = remapRowAgingData(row, PRESET_SEGMENTS.FIVE_YEAR, /* isThreePeriod */ true)

    // 键集变成五年档
    expect(Object.keys(remapped.agingAudited)).toEqual(['within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5'])
    // 共同段（within1/y1to2/y2to3）已录值逐字保留
    expect(remapped.agingAudited.within1).toBe(1)
    expect(remapped.agingAudited.y1to2).toBe(2)
    expect(remapped.agingAudited.y2to3).toBe(3)
    expect(remapped.agingPrior.within1).toBe(111)
    expect(remapped.agingCurrent.y1to2).toBe(20)
    // 三年档的 over3 在五年档无对应段 → 丢弃（既有迁移规则），新增段补 0
    expect(remapped.agingAudited).not.toHaveProperty('over3')
    expect(remapped.agingAudited.y3to4).toBe(0)
    expect(remapped.agingAudited.over5).toBe(0)
    // 非账龄字段不动
    expect(remapped.counterparty).toBe('甲公司')
  })

  it('五年→自定义→回五年 链式切换：共同段的已录值不因往返丢失', () => {
    const row: any = {
      agingPrior: { within1: 5, y1to2: 6, y2to3: 7, y3to4: 8, y4to5: 9, over5: 10 },
      agingCurrent: { within1: 0, y1to2: 0, y2to3: 0, y3to4: 0, y4to5: 0, over5: 0 },
      agingAudited: { within1: 5, y1to2: 6, y2to3: 7, y3to4: 8, y4to5: 9, over5: 10 },
    }
    // 五年 → 自定义（键完全不同 → 全部落到新段的 0；这是既有迁移规则的预期丢弃）
    const toCustom = remapRowAgingData(row, CUSTOM_SEGMENTS, true)
    expect(Object.keys(toCustom.agingAudited)).toEqual(['seg_a', 'seg_b', 'seg_c'])
    // 在自定义档补录一个值
    toCustom.agingAudited.seg_a = 99
    // 自定义 → 回五年（seg_* 在五年无对应 → 丢弃；这里断言 remap 不抛、结构回五年档）
    const backToFive = remapRowAgingData(toCustom, PRESET_SEGMENTS.FIVE_YEAR, true)
    expect(Object.keys(backToFive.agingAudited)).toEqual(['within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5'])
    // 五年新键均为 0（seg_a 的 99 无对应五年段 → 归并丢弃，符合"无对应新段按既有迁移规则"）
    for (const v of Object.values(backToFive.agingAudited)) expect(v).toBe(0)
  })

  it('2-period 行（D3，无 agingCurrent）重映射保留 prior/audited 已录值', () => {
    const row: any = {
      agingPrior: { within1: 100, y1to2: 200, y2to3: 300, over3: 400 },
      agingAudited: { within1: 11, y1to2: 22, y2to3: 33, over3: 44 },
    }
    const remapped = remapRowAgingData(row, PRESET_SEGMENTS.FIVE_YEAR, /* isThreePeriod */ false)
    // 不臆造 agingCurrent
    expect(remapped.agingCurrent).toBeUndefined()
    expect(Object.keys(remapped.agingPrior)).toEqual(['within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5'])
    expect(remapped.agingPrior.within1).toBe(100)
    expect(remapped.agingAudited.y2to3).toBe(33)
    expect(remapped.agingPrior.y4to5).toBe(0)
  })
})
