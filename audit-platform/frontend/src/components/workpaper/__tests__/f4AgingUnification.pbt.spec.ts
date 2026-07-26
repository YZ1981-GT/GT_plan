/**
 * F4 账龄枚举统一 — 属性化测试与 3 年段零回归基线
 *
 * Spec: .kiro/specs/f4-aging-enum-unification/ Task 1.2 / 7.1
 *
 * - Property 1：段驱动聚合 = 逐行逐段求和
 * - Property 2：Nested 优先于 Legacy
 * - Property 3：段切换保同 key / 补新段 / 丢废段
 * - Property 4：Over_One_Year_Keys 由 dayFrom>=366 派生
 * - Property 6：3 年段结果与迁移前口径逐项一致（零回归基线）
 * - Property 8：rowKey 映射稳定
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { remapRowAgingData } from '@/composables/useAgingMigration'
import {
  aggregateAgingBySegments,
  f4AgingRowKey,
  f4AgingValue,
  overOneYearKeys,
  sumRowAging,
  F4_RESIDUAL_ROW_KEY,
} from '../composables/f4AgingModel'
import { computeF4DetailRow, migrateF4DetailRows } from '../composables/useF4Detail'
import {
  aggregateF4Detail,
  buildF4AgingDefaults,
  F4_AGING_DEFAULTS,
} from '../composables/useF4Adjudication'

const THREE = PRESET_SEGMENTS.THREE_YEAR as AgingSegment[]
const FIVE = PRESET_SEGMENTS.FIVE_YEAR as AgingSegment[]
const NUM_RUNS = 20

const amount = () => fc.integer({ min: -100000, max: 100000 })

function arbSegments(): fc.Arbitrary<AgingSegment[]> {
  return fc.constantFrom(THREE, FIVE)
}

function arbRow(segments: AgingSegment[]): fc.Arbitrary<Record<string, any>> {
  return fc.record({
    agingCurrent: fc.dictionary(fc.constantFrom(...segments.map((s) => s.key)), amount()),
    agingAudited: fc.dictionary(fc.constantFrom(...segments.map((s) => s.key)), amount()),
  })
}

describe('Property 1：段驱动聚合 = 逐行逐段求和', () => {
  it('任意段集合 × 任意行集合下聚合等于手工双层求和', () => {
    fc.assert(
      fc.property(
        arbSegments().chain((segs) =>
          fc.tuple(fc.constant(segs), fc.array(arbRow(segs), { maxLength: 6 })),
        ),
        ([segs, rows]) => {
          const keys = segs.map((s) => String(s.key))
          for (const period of ['current', 'audited'] as const) {
            const agg = aggregateAgingBySegments(rows, period, keys)
            for (const key of keys) {
              const manual = rows.reduce((sum, r) => sum + f4AgingValue(r, period, key), 0)
              expect(agg[key]).toBeCloseTo(manual, 6)
            }
          }
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('Property 2：Nested 优先于 Legacy', () => {
  it('同时含 nested 与扁平字段时取 nested', () => {
    fc.assert(
      fc.property(amount(), amount(), (nested, flat) => {
        const row = { agingCurrent: { within1: nested }, unadjustedAgingLt1: flat }
        expect(f4AgingValue(row, 'current', 'within1')).toBe(nested)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('仅含扁平字段时回退 legacy（3 年段一一对应）', () => {
    const row = {
      unadjustedAgingLt1: 10,
      unadjustedAging1to2: 20,
      unadjustedAging2to3: 30,
      unadjustedAgingGt3: 40,
    }
    expect(sumRowAging(row, 'current', THREE.map((s) => String(s.key)))).toBe(100)
  })
})

describe('Property 3：段切换保同 key / 补新段 / 丢废段', () => {
  it('A→B 切换后 A∩B 保金额、B−A 为 0、A−B 不出现', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<[AgingSegment[], AgingSegment[]]>([THREE, FIVE], [FIVE, THREE]),
        fc.array(amount(), { minLength: 6, maxLength: 6 }),
        ([from, to], amounts) => {
          const agingCurrent: Record<string, number> = {}
          from.forEach((seg, i) => { agingCurrent[String(seg.key)] = amounts[i] ?? 0 })
          const next = remapRowAgingData({ agingCurrent }, to, false)
          const fromKeys = new Set(from.map((s) => String(s.key)))
          const toKeys = to.map((s) => String(s.key))
          expect(Object.keys(next.agingCurrent).sort()).toEqual([...toKeys].sort())
          for (const key of toKeys) {
            if (fromKeys.has(key)) expect(next.agingCurrent[key]).toBe(agingCurrent[key])
            else expect(next.agingCurrent[key]).toBe(0)
          }
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })
})

describe('Property 4：Over_One_Year_Keys 由 dayFrom 派生', () => {
  it('恒等于 dayFrom>=366 的段 key', () => {
    fc.assert(
      fc.property(arbSegments(), (segs) => {
        expect(overOneYearKeys(segs)).toEqual(
          segs.filter((s) => Number(s.dayFrom) >= 366).map((s) => String(s.key)),
        )
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('残差行不属于任何段（不计入 1 年以上）', () => {
    expect(overOneYearKeys(FIVE)).not.toContain(F4_RESIDUAL_ROW_KEY)
    expect(overOneYearKeys(THREE)).not.toContain(F4_RESIDUAL_ROW_KEY)
  })
})

describe('Property 8：rowKey 映射稳定', () => {
  it('3 年段恒映射既有 4 键；其它段恒为段 key；映射幂等', () => {
    expect(THREE.map((s) => f4AgingRowKey(String(s.key)))).toEqual([
      'within1year', '1to2year', '2to3year', '3yearplus',
    ])
    expect(f4AgingRowKey('y4to5')).toBe('y4to5')
    for (const seg of FIVE) {
      const once = f4AgingRowKey(String(seg.key))
      expect(f4AgingRowKey(String(seg.key))).toBe(once)
    }
  })
})

describe('Property 6：3 年段零回归基线', () => {
  it('F4-1 按账龄默认行 = 迁移前固定 4 档 + 残差行（rowKey/label 逐项一致）', () => {
    const built = buildF4AgingDefaults(THREE)
    expect(built.map((r) => r.rowKey)).toEqual(F4_AGING_DEFAULTS.map((r) => r.rowKey))
    expect(built.map((r) => r.label)).toEqual(F4_AGING_DEFAULTS.map((r) => r.label))
  })

  it('5 年段在既有 4 键之外追加段 key，残差行仍在末尾', () => {
    const built = buildF4AgingDefaults(FIVE)
    expect(built.map((r) => r.rowKey)).toEqual([
      'within1year', '1to2year', '2to3year', 'y3to4', 'y4to5', 'over5', F4_RESIDUAL_ROW_KEY,
    ])
  })

  it('仅含迁移前扁平账龄的行：明细勾稽与账龄合计与迁移前一致', () => {
    const stored = migrateF4DetailRows(JSON.stringify([{
      creditor: '甲公司',
      openingUnadjusted: 1000,
      currentDebit: 200,
      currentCredit: 500,
      entityReclassification: 50,
      unadjustedAgingLt1: 900,
      unadjustedAging1to2: 450,
      closingAje: -20,
      closingRje: 10,
      auditedAgingLt1: 890,
      auditedAging1to2: 450,
    }]))[0]
    const row = computeF4DetailRow(stored, THREE)
    expect(row.closingUnadjusted).toBe(1350)
    expect(row.closingAdjusted).toBe(1340)
    expect(row.unadjustedAgingTotal).toBe(1350)
    expect(row.auditedAgingTotal).toBe(1340)
    expect(row.unadjustedAgingMismatch).toBe(false)
    expect(row.auditedAgingMismatch).toBe(false)
    // 兼容派生的扁平字段仍等于迁移前值
    expect(row.unadjustedAgingLt1).toBe(900)
    expect(row.auditedAging1to2).toBe(450)
  })

  it('F4-1 明细聚合（3 年段）rowKey 与金额与迁移前一致', () => {
    const detail = JSON.stringify([{
      creditor: '甲公司',
      paymentNature: '货款',
      closingUnadjusted: 120,
      unadjustedAgingLt1: 80,
      closingAje: 10,
      closingRje: 2,
      closingAdjusted: 130,
      auditedAgingLt1: 85,
    }])
    const legacy = aggregateF4Detail(detail)
    const explicit = aggregateF4Detail(detail, THREE)
    expect(explicit).toEqual(legacy)
    expect(legacy.aging.within1year.closingUnadjusted).toBe(80)
    expect(legacy.aging.within1year.closingAje).toBe(5)
    expect(legacy.aging[F4_RESIDUAL_ROW_KEY].closingUnadjusted).toBe(40)
    expect(legacy.aging[F4_RESIDUAL_ROW_KEY].closingRje).toBe(2)
  })

  it('5 年段明细聚合：账龄行按段扩展且合计不变', () => {
    const detail = JSON.stringify([{
      creditor: '乙公司',
      closingUnadjusted: 100,
      agingCurrent: { within1: 40, y1to2: 20, y2to3: 10, y3to4: 10, y4to5: 10, over5: 10 },
      closingAdjusted: 100,
      agingAudited: { within1: 40, y1to2: 20, y2to3: 10, y3to4: 10, y4to5: 10, over5: 10 },
    }])
    const agg = aggregateF4Detail(detail, FIVE)
    expect(Object.keys(agg.aging).sort()).toEqual(
      [...FIVE.map((s) => f4AgingRowKey(String(s.key))), F4_RESIDUAL_ROW_KEY].sort(),
    )
    const total = Object.values(agg.aging).reduce((s, v) => s + v.closingUnadjusted, 0)
    expect(total).toBeCloseTo(100, 6)
  })
})
