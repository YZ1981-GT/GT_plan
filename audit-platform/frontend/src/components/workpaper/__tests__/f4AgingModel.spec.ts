/**
 * F4 账龄枚举统一 — 迁移与派生纯函数测试
 *
 * Spec: .kiro/specs/f4-aging-enum-unification/
 * Properties: 1(段驱动聚合) 2(nested优先) 3(段切换) 4(1年以上派生) 5(残差不计入) 7(勾稽按段) 8(rowKey映射)
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import {
  migrateF4FlatToNested,
  isLegacyF4Format,
  remapRowAgingData,
} from '@/composables/useAgingMigration'
import {
  LEGACY_AGING_ROWKEY,
  F4_RESIDUAL_ROW_KEY,
  f4AgingRowKey,
  overOneYearKeys,
  overOneYearRowKeys,
  f4AgingValue,
  sumRowAging,
  aggregateAgingBySegments,
  projectLegacyFlatAging,
  createEmptyF4Aging,
} from '../composables/f4AgingModel'

const THREE = PRESET_SEGMENTS.THREE_YEAR as AgingSegment[]
const FIVE = PRESET_SEGMENTS.FIVE_YEAR as AgingSegment[]
const keys = (segs: AgingSegment[]) => segs.map((s) => s.key)

describe('migrateF4FlatToNested（Property 2）', () => {
  it('仅扁平字段 → 映射到 THREE_YEAR 段 key，输出不含扁平字段', () => {
    const row = migrateF4FlatToNested({
      rowId: 'r1',
      creditor: '甲公司',
      unadjustedAgingLt1: 100,
      unadjustedAging1to2: 50,
      unadjustedAging2to3: 20,
      unadjustedAgingGt3: 10,
      auditedAgingLt1: 95,
      auditedAging1to2: 50,
      auditedAging2to3: 20,
      auditedAgingGt3: 10,
    })
    expect(row.agingCurrent).toEqual({ within1: 100, y1to2: 50, y2to3: 20, over3: 10 })
    expect(row.agingAudited).toEqual({ within1: 95, y1to2: 50, y2to3: 20, over3: 10 })
    expect(row.creditor).toBe('甲公司')
    expect('unadjustedAgingLt1' in row).toBe(false)
    expect('auditedAgingGt3' in row).toBe(false)
  })

  it('历史别名（aging1Year / adjustedAging1 等）也能迁移', () => {
    const row = migrateF4FlatToNested({
      aging1Year: 10,
      aging1to2Year: 20,
      aging2to3Year: 30,
      aging3YearPlus: 40,
      adjustedAging1: 11,
      adjustedAging2: 21,
      adjustedAging3: 31,
      adjustedAging4: 41,
    })
    expect(row.agingCurrent).toEqual({ within1: 10, y1to2: 20, y2to3: 30, over3: 40 })
    expect(row.agingAudited).toEqual({ within1: 11, y1to2: 21, y2to3: 31, over3: 41 })
    expect('aging1Year' in row).toBe(false)
  })

  it('nested 与扁平并存时以 nested 为准（忽略扁平）', () => {
    const row = migrateF4FlatToNested({
      agingCurrent: { within1: 7, y1to2: 3 },
      agingAudited: { within1: 6 },
      unadjustedAgingLt1: 999,
      auditedAgingLt1: 888,
    })
    expect(row.agingCurrent).toEqual({ within1: 7, y1to2: 3 })
    expect(row.agingAudited).toEqual({ within1: 6 })
  })

  it('异常值（null/NaN/字符串）按 0 处理，不抛错', () => {
    const row = migrateF4FlatToNested({
      unadjustedAgingLt1: null,
      unadjustedAging1to2: 'abc',
      unadjustedAging2to3: undefined,
      unadjustedAgingGt3: NaN,
    })
    expect(row.agingCurrent).toEqual({ within1: 0, y1to2: 0, y2to3: 0, over3: 0 })
  })

  it('isLegacyF4Format 识别规范字段与历史别名', () => {
    expect(isLegacyF4Format({ unadjustedAgingLt1: 1 })).toBe(true)
    expect(isLegacyF4Format({ adjustedAging3: 1 })).toBe(true)
    expect(isLegacyF4Format({ agingCurrent: { within1: 1 } })).toBe(false)
    expect(isLegacyF4Format(null)).toBe(false)
  })
})

describe('f4AgingRowKey / LEGACY_AGING_ROWKEY（Property 8）', () => {
  it('3 年段恒映射为既有 4 个 rowKey', () => {
    expect(keys(THREE).map(f4AgingRowKey)).toEqual(['within1year', '1to2year', '2to3year', '3yearplus'])
  })

  it('映射表未覆盖的段直接用段 key，且映射稳定（多次一致）', () => {
    expect(f4AgingRowKey('y3to4')).toBe('y3to4')
    expect(f4AgingRowKey('seg_custom_1')).toBe('seg_custom_1')
    expect(f4AgingRowKey('over3')).toBe(f4AgingRowKey('over3'))
    expect(LEGACY_AGING_ROWKEY[F4_RESIDUAL_ROW_KEY]).toBeUndefined()
  })
})

describe('overOneYearKeys（Property 4 / 5）', () => {
  it('3 年段 → 1-2/2-3/3年以上；5 年段 → 5 段', () => {
    expect(overOneYearKeys(THREE)).toEqual(['y1to2', 'y2to3', 'over3'])
    expect(overOneYearKeys(FIVE)).toEqual(['y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5'])
  })

  it('rowKey 版本不含残差行', () => {
    expect(overOneYearRowKeys(THREE)).toEqual(['1to2year', '2to3year', '3yearplus'])
    expect(overOneYearRowKeys(THREE)).not.toContain(F4_RESIDUAL_ROW_KEY)
  })

  it('PBT：恒等于 dayFrom>=366 的段 key，与段数量/命名无关', () => {
    const segArb = fc.array(
      fc.record({
        key: fc.string({ minLength: 1, maxLength: 6 }).filter((s) => /^[a-zA-Z0-9_]+$/.test(s)),
        label: fc.constant('seg'),
        dayFrom: fc.integer({ min: 0, max: 4000 }),
        dayTo: fc.constant(null),
      }),
      { minLength: 0, maxLength: 8 },
    )
    fc.assert(
      fc.property(segArb, (segs) => {
        const expected = segs.filter((s) => s.dayFrom >= 366).map((s) => s.key)
        expect(overOneYearKeys(segs as AgingSegment[])).toEqual(expected)
      }),
      { numRuns: 40 },
    )
  })
})

describe('f4AgingValue / sumRowAging（Property 2 / 7）', () => {
  it('nested 优先；nested 缺该键回退 legacy 扁平；两者都缺为 0', () => {
    const row = { agingCurrent: { y1to2: 9 }, unadjustedAgingLt1: 7, unadjustedAging2to3: 3 }
    expect(f4AgingValue(row, 'current', 'y1to2')).toBe(9)
    expect(f4AgingValue(row, 'current', 'within1')).toBe(7)
    expect(f4AgingValue(row, 'current', 'y2to3')).toBe(3)
    expect(f4AgingValue(row, 'current', 'y3to4')).toBe(0)
  })

  it('单行按段合计（勾稽基准）', () => {
    const row = { agingAudited: { within1: 100, y1to2: 20, y2to3: 5, over3: 1 } }
    expect(sumRowAging(row, 'audited', keys(THREE))).toBe(126)
    expect(sumRowAging(row, 'audited', overOneYearKeys(THREE))).toBe(26)
  })
})

describe('aggregateAgingBySegments（Property 1）', () => {
  it('聚合等于逐行逐段求和；未出现段补 0', () => {
    const rows = [
      { agingCurrent: { within1: 100, y1to2: 10 } },
      { agingCurrent: { within1: 50, over3: 5 } },
      { unadjustedAging1to2: 7 }, // legacy 回退
    ]
    const agg = aggregateAgingBySegments(rows, 'current', keys(THREE))
    expect(agg).toEqual({ within1: 150, y1to2: 17, y2to3: 0, over3: 5 })
  })

  it('PBT：任意行集合 × 任意段集合，聚合 = 手工 map+reduce', () => {
    const rowArb = fc.record({
      agingAudited: fc.dictionary(
        fc.constantFrom('within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5', 'over3'),
        fc.integer({ min: -1000, max: 1000 }),
      ),
    })
    fc.assert(
      fc.property(fc.array(rowArb, { maxLength: 12 }), fc.constantFrom(THREE, FIVE), (rows, segs) => {
        const segKeys = keys(segs)
        const agg = aggregateAgingBySegments(rows, 'audited', segKeys)
        for (const k of segKeys) {
          const manual = rows.reduce((s, r: any) => s + (Number(r.agingAudited?.[k]) || 0), 0)
          expect(agg[k]).toBe(manual)
        }
      }),
      { numRuns: 40 },
    )
  })
})

describe('remapRowAgingData 用于 F4 段切换（Property 3）', () => {
  it('同 key 保值 / 新增段补 0 / 废弃段丢弃', () => {
    const row = { agingCurrent: { within1: 10, y1to2: 20, y2to3: 30, over3: 40 }, agingAudited: { within1: 1 } }
    const next = remapRowAgingData(row, FIVE, false)
    expect(next.agingCurrent).toEqual({ within1: 10, y1to2: 20, y2to3: 30, y3to4: 0, y4to5: 0, over5: 0 })
    expect('over3' in next.agingCurrent).toBe(false)
    expect(next.agingAudited.within1).toBe(1)
    expect(next.agingAudited.over5).toBe(0)
  })

  it('PBT：A→B 后 A∩B 保值、B−A 为 0、A−B 消失', () => {
    fc.assert(
      fc.property(
        fc.dictionary(fc.constantFrom('within1', 'y1to2', 'y2to3', 'over3'), fc.integer({ min: 0, max: 999 })),
        fc.constantFrom(THREE, FIVE),
        (data, target) => {
          const next = remapRowAgingData({ agingCurrent: { ...data }, agingAudited: {} }, target, false)
          const targetKeys = keys(target)
          expect(Object.keys(next.agingCurrent).sort()).toEqual([...targetKeys].sort())
          for (const k of targetKeys) {
            expect(next.agingCurrent[k]).toBe(k in data ? data[k] : 0)
          }
        },
      ),
      { numRuns: 40 },
    )
  })
})

describe('projectLegacyFlatAging（3 年段兼容层零回归）', () => {
  it('3 年段一一对应（迁移前口径逐字节相同）', () => {
    const row = { agingAudited: { within1: 100, y1to2: 20, y2to3: 5, over3: 1 } }
    expect(projectLegacyFlatAging(row, 'audited', THREE)).toEqual({
      auditedAgingLt1: 100,
      auditedAging1to2: 20,
      auditedAging2to3: 5,
      auditedAgingGt3: 1,
    })
  })

  it('5 年段：Gt3 = dayFrom>=1096 各段之和（兼容投影）', () => {
    const row = { agingCurrent: { within1: 1, y1to2: 2, y2to3: 3, y3to4: 4, y4to5: 5, over5: 6 } }
    expect(projectLegacyFlatAging(row, 'current', FIVE)).toEqual({
      unadjustedAgingLt1: 1,
      unadjustedAging1to2: 2,
      unadjustedAging2to3: 3,
      unadjustedAgingGt3: 15,
    })
  })
})

describe('createEmptyF4Aging', () => {
  it('按段全零', () => {
    expect(createEmptyF4Aging(THREE)).toEqual({ within1: 0, y1to2: 0, y2to3: 0, over3: 0 })
    expect(createEmptyF4Aging([])).toEqual({})
  })
})
