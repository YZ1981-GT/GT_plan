/**
 * useD7CrossSheet Property-Based Tests
 *
 * 使用 fast-check 验证 D7 合同负债跨Sheet联动的核心 correctness properties。
 * numRuns: 100，覆盖 Property 4/5/12。
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Tasks: 4.2, 4.3, 4.4
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  aggregateByNature,
  aggregateByAging,
  type DetailRow,
} from '../composables/useD7FormulaEngine'

// ─── Shared generators ──────────────────────────────────────────────────────

const finiteFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min, max, noNaN: true, noDefaultInfinity: true })

const NATURE_TYPES = ['预收货款', '开发项目预收款', '预收工程款', '其他'] as const

/** 自定义 DetailRow 生成器（性质聚合测试用） */
const detailRowForNature = (): fc.Arbitrary<DetailRow> =>
  fc.record({
    natureType: fc.constantFrom(...NATURE_TYPES),
    endAudited: finiteFloat(),
    endAging1: finiteFloat(),
    endAging2: finiteFloat(),
    endAging3: finiteFloat(),
    endAging4: finiteFloat(),
  })

/** 自定义 DetailRow 生成器（账龄聚合测试用） */
const detailRowForAging = (): fc.Arbitrary<DetailRow> =>
  fc.record({
    natureType: fc.constantFrom(...NATURE_TYPES),
    endAudited: finiteFloat(),
    endAging1: finiteFloat(),
    endAging2: finiteFloat(),
    endAging3: finiteFloat(),
    endAging4: finiteFloat(),
  })

/** 自定义 DetailRow 生成器（交叉验证用：endAudited = SUM(endAging1~4) 约束） */
const detailRowForCrossValidation = (): fc.Arbitrary<DetailRow> =>
  fc.tuple(
    fc.constantFrom(...NATURE_TYPES),
    finiteFloat(),
    finiteFloat(),
    finiteFloat(),
    finiteFloat(),
  ).map(([natureType, a1, a2, a3, a4]) => ({
    natureType,
    endAudited: a1 + a2 + a3 + a4,
    endAging1: a1,
    endAging2: a2,
    endAging3: a3,
    endAging4: a4,
  }))

// ─── Property 4: 按性质聚合正确性（D7-2→D7-1）──────────────────────────────

describe('Property 4: 按性质聚合正确性（D7-2→D7-1）', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 4: 按性质聚合正确性（D7-2→D7-1）**
   *
   * For any 明细表D7-2行数据集，按"款项性质(natureType)"列分组后，
   * 每组的endAudited之和应等于 aggregateByNature 返回的对应类别值。
   *
   * **Validates: Requirements 3.1**
   */
  it('各类别 aggregateByNature sum === 手动 filter+reduce 结果', () => {
    fc.assert(
      fc.property(
        fc.array(detailRowForNature(), { minLength: 0, maxLength: 30 }),
        (rows) => {
          const result = aggregateByNature(rows, 'endAudited')

          // 手动 filter+reduce 对照
          for (const natureType of NATURE_TYPES) {
            const expected = rows
              .filter(r => r.natureType === natureType)
              .reduce((sum, r) => sum + r.endAudited, 0)
            const actual = result[natureType] || 0
            expect(Math.abs(actual - expected)).toBeLessThan(1e-6)
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Property 5: 按账龄聚合正确性（D7-2→D7-1）──────────────────────────────

describe('Property 5: 按账龄聚合正确性（D7-2→D7-1）', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 5: 按账龄聚合正确性（D7-2→D7-1）**
   *
   * For any 明细表D7-2行数据集，对endAging1~endAging4各列分别SUM，
   * 其结果应等于 aggregateByAging 返回的对应段值。
   *
   * **Validates: Requirements 3.2**
   */
  it('各账龄段 aggregateByAging sum === 手动 map+reduce 结果', () => {
    fc.assert(
      fc.property(
        fc.array(detailRowForAging(), { minLength: 0, maxLength: 30 }),
        (rows) => {
          const result = aggregateByAging(rows)

          // 手动 map+reduce 对照
          const expectedWithin1Year = rows.reduce((sum, r) => sum + r.endAging1, 0)
          const expectedYear1to2 = rows.reduce((sum, r) => sum + r.endAging2, 0)
          const expectedYear2to3 = rows.reduce((sum, r) => sum + r.endAging3, 0)
          const expectedOver3Years = rows.reduce((sum, r) => sum + r.endAging4, 0)

          expect(Math.abs(result.within1Year - expectedWithin1Year)).toBeLessThan(1e-6)
          expect(Math.abs(result.year1to2 - expectedYear1to2)).toBeLessThan(1e-6)
          expect(Math.abs(result.year2to3 - expectedYear2to3)).toBeLessThan(1e-6)
          expect(Math.abs(result.over3Years - expectedOver3Years)).toBeLessThan(1e-6)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ─── Property 12: 性质分类合计 = 账龄分类合计（双区块交叉验证）──────────────

describe('Property 12: 性质分类合计 = 账龄分类合计（双区块交叉验证）', () => {
  /**
   * **Feature: d7-contract-liabilities, Property 12: 性质分类合计 = 账龄分类合计（双区块交叉验证）**
   *
   * For any 明细表D7-2行数据集（约束：endAudited = SUM(endAging1~4)），
   * 按性质聚合的endAudited合计 === 按账龄聚合的endAudited合计。
   * 当每行账龄字段之和等于该行endAudited时恒成立。
   *
   * **Validates: Requirements 2.9**
   */
  it('当 endAudited = SUM(endAging1~4) 时，性质合计 === 账龄合计', () => {
    fc.assert(
      fc.property(
        fc.array(detailRowForCrossValidation(), { minLength: 0, maxLength: 30 }),
        (rows) => {
          // 按性质聚合合计 = SUM(各类别endAudited)
          const natureAgg = aggregateByNature(rows, 'endAudited')
          const natureTotal = Object.values(natureAgg).reduce((sum, v) => sum + v, 0)

          // 按账龄聚合合计 = SUM(endAging1~4 across all rows)
          const agingAgg = aggregateByAging(rows)
          const agingTotal = agingAgg.within1Year + agingAgg.year1to2 +
            agingAgg.year2to3 + agingAgg.over3Years

          // 交叉验证：当约束成立时恒等
          expect(Math.abs(natureTotal - agingTotal)).toBeLessThan(1e-4)
        }
      ),
      { numRuns: 100 }
    )
  })
})
