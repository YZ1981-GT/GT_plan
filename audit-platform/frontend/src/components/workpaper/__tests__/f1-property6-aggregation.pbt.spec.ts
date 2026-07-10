/**
 * F1 Property 6 PBT: 按预付类型聚合正确性
 *
 * 验证 aggregateByNature 和 aggregateByAging 纯函数的正确性：
 * - 按款项性质分组SUM结果应等于手动 filter + reduce 结果
 * - 按账龄聚合应等于各行对应字段之和
 *
 * **Validates: Requirements 3.1, 3.2, 4.1, 4.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  aggregateByNature,
  aggregateByAging,
  type DetailRowForFormula,
} from '../composables/useF1FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

const NATURE_VALUES = ['预付货款', '预付服务费', '预付租金', '其他'] as const

const detailRowArb: fc.Arbitrary<DetailRowForFormula> = fc.record({
  nature: fc.constantFrom(...NATURE_VALUES),
  endAudited: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorAudited: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  agingAudited: fc.record({
    within1: fc.float({ min: 0, max: 1e9, noNaN: true }),
    y1to2: fc.float({ min: 0, max: 1e9, noNaN: true }),
    y2to3: fc.float({ min: 0, max: 1e9, noNaN: true }),
    over3: fc.float({ min: 0, max: 1e9, noNaN: true }),
  }),
})

const detailRowsArb = fc.array(detailRowArb, { minLength: 0, maxLength: 20 })

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 6: 按预付类型聚合正确性', () => {
  /**
   * **Property 6a: aggregateByNature endAudited 聚合 === 手动 filter+reduce**
   *
   * 对任意 DetailRow[] 数组，按 nature 分组对 endAudited 求和的结果，
   * 应等于逐一筛选 nature 相同的行再 reduce 求和。
   *
   * **Validates: Requirements 3.1, 3.2**
   */
  it('aggregateByNature(rows, "endAudited") 等于手动 filter+reduce', () => {
    fc.assert(
      fc.property(detailRowsArb, (rows) => {
        const result = aggregateByNature(rows, 'endAudited')

        // 手动聚合验证
        const manual: Record<string, number> = {}
        for (const row of rows) {
          const key = row.nature || '其他'
          if (!manual[key]) manual[key] = 0
          manual[key] += row.endAudited
        }

        // 所有 key 的结果应一致
        const allKeys = new Set([...Object.keys(result), ...Object.keys(manual)])
        for (const key of allKeys) {
          const diff = Math.abs((result[key] || 0) - (manual[key] || 0))
          if (diff > 1e-6) return false
        }
        return true
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 6b: aggregateByNature priorAudited 聚合 === 手动 filter+reduce**
   *
   * **Validates: Requirements 3.2**
   */
  it('aggregateByNature(rows, "priorAudited") 等于手动 filter+reduce', () => {
    fc.assert(
      fc.property(detailRowsArb, (rows) => {
        const result = aggregateByNature(rows, 'priorAudited')

        const manual: Record<string, number> = {}
        for (const row of rows) {
          const key = row.nature || '其他'
          if (!manual[key]) manual[key] = 0
          manual[key] += row.priorAudited
        }

        const allKeys = new Set([...Object.keys(result), ...Object.keys(manual)])
        for (const key of allKeys) {
          const diff = Math.abs((result[key] || 0) - (manual[key] || 0))
          if (diff > 1e-6) return false
        }
        return true
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 6c: aggregateByAging 聚合 === 各行对应账龄字段之和**
   *
   * **Validates: Requirements 4.1, 4.2**
   */
  it('aggregateByAging(rows) 各字段等于 SUM(row.agingAudited.field)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rows) => {
        const result = aggregateByAging(rows)

        let within1 = 0, y1to2 = 0, y2to3 = 0, over3 = 0
        for (const row of rows) {
          within1 += row.agingAudited.within1
          y1to2 += row.agingAudited.y1to2
          y2to3 += row.agingAudited.y2to3
          over3 += row.agingAudited.over3
        }

        return (
          Math.abs(result.within1 - within1) < 1e-6 &&
          Math.abs(result.y1to2 - y1to2) < 1e-6 &&
          Math.abs(result.y2to3 - y2to3) < 1e-6 &&
          Math.abs(result.over3 - over3) < 1e-6
        )
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 6d: 空数组聚合结果为全零**
   *
   * **Validates: Requirements 3.1**
   */
  it('空数组 aggregateByNature 返回空对象，aggregateByAging 返回全零', () => {
    const emptyNature = aggregateByNature([], 'endAudited')
    expect(Object.keys(emptyNature)).toHaveLength(0)

    const emptyAging = aggregateByAging([])
    expect(emptyAging.within1).toBe(0)
    expect(emptyAging.y1to2).toBe(0)
    expect(emptyAging.y2to3).toBe(0)
    expect(emptyAging.over3).toBe(0)
  })
})
