/**
 * useD3Analysis PBT 测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D3-4 分析表核心逻辑：Top5债务人分析正确性。
 *
 * 测试纯函数逻辑（computeTop5），不依赖 Vue 响应式。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { computeTop5 } from '../composables/useD3Analysis'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 非负金额生成器 */
const amountArb = fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })

/** DetailRow（仅top5相关字段）生成器 */
const detailRowArb = fc.record({
  customerName: fc.string({ minLength: 1, maxLength: 20 }),
  endAudited: amountArb,
  priorAudited: amountArb,
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD3Analysis - Property-Based Tests', () => {
  /**
   * **Feature: d3-prepaid-accounts, Property 17: Top5债务人分析正确性**
   *
   * For any 明细表行数据集（N行），Top5应为按期末余额降序排列的前5行（或全部行若N<5）；
   * 当Top5余额之和占合计超过50%时应产生集中度警告。
   *
   * **Validates: Requirements 8.4, 8.5**
   */
  describe('Property 17: Top5债务人分析正确性', () => {
    it('top5为前5大余额降序排列', () => {
      fc.assert(
        fc.property(
          fc.array(detailRowArb, { minLength: 1, maxLength: 50 }),
          (rows) => {
            const { top5 } = computeTop5(rows)

            // Should have at most 5 entries
            expect(top5.length).toBeLessThanOrEqual(5)
            // Should have min(N, 5) entries
            expect(top5.length).toBe(Math.min(rows.length, 5))

            // Should be sorted descending by endAudited
            for (let i = 1; i < top5.length; i++) {
              expect(top5[i - 1].endAudited).toBeGreaterThanOrEqual(top5[i].endAudited)
            }

            // Each top5 entry should be among the top5 largest endAudited values
            const sortedOriginal = [...rows].sort((a, b) => b.endAudited - a.endAudited)
            for (let i = 0; i < top5.length; i++) {
              expect(top5[i].endAudited).toBeCloseTo(sortedOriginal[i].endAudited, 4)
            }
          }
        ),
        { numRuns: 100 }
      )
    })

    it('>50%集中度时有警告', () => {
      fc.assert(
        fc.property(
          fc.array(detailRowArb, { minLength: 1, maxLength: 50 }),
          (rows) => {
            const { top5, concentrationWarning } = computeTop5(rows)

            const totalEndAudited = rows.reduce((sum, r) => sum + r.endAudited, 0)
            const top5Total = top5.reduce((sum, r) => sum + r.endAudited, 0)

            if (totalEndAudited > 0 && top5Total / totalEndAudited > 0.5) {
              expect(concentrationWarning).not.toBeNull()
              expect(concentrationWarning).toContain('集中度')
            } else if (totalEndAudited === 0) {
              // Total is 0, no concentration warning
              expect(concentrationWarning).toBeNull()
            } else {
              expect(concentrationWarning).toBeNull()
            }
          }
        ),
        { numRuns: 100 }
      )
    })

    it('空数组时返回空top5且无警告', () => {
      const { top5, concentrationWarning } = computeTop5([])
      expect(top5).toHaveLength(0)
      expect(concentrationWarning).toBeNull()
    })

    it('top5 changeAmount = endAudited - priorAudited', () => {
      fc.assert(
        fc.property(
          fc.array(detailRowArb, { minLength: 1, maxLength: 10 }),
          (rows) => {
            const { top5 } = computeTop5(rows)
            for (const debtor of top5) {
              expect(debtor.changeAmount).toBeCloseTo(
                debtor.endAudited - debtor.priorAudited, 4
              )
            }
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
