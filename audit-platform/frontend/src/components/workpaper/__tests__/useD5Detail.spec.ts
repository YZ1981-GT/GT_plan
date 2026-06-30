/**
 * useD5Detail PBT — Property 10 & Property 7
 *
 * Property 10: D5-2行内公式链正确性
 * Property 7: 动态行添加保持结构不变量
 *
 * Feature: d5-receivables-financing
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { recalcRow, createEmptyRow } from '../composables/useD5Detail'
import type { DetailRow } from '../composables/useD5Detail'

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD5Detail - Property-Based Tests', () => {
  /**
   * **Feature: d5-receivables-financing, Property 10: D5-2行内公式链正确性**
   *
   * For any 明细行输入值组合 (C,D,E,H,I,K,M,N)，以下公式链必须成立：
   * - 期初审定 F = C + D + E
   * - 期末余额 J = F + H - I
   * - 期末未审余额 L = J + K
   * - 期末审定余额 O = L + M + N
   *
   * **Validates: Requirements 4.3**
   */
  describe('Property 10: D5-2行内公式链正确性', () => {
    it('recalcRow produces F=C+D+E; J=F+H-I; L=J+K; O=L+M+N', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // C: priorUnadjusted
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // D: priorAje
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // E: priorRje
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // H: periodIncrease
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // I: periodDecrease
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // K: entityReclass
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // M: endAje
          fc.float({ min: -1e9, max: 1e9, noNaN: true }), // N: endRje
          (C, D, E, H, I, K, M, N) => {
            const row: DetailRow = {
              rowId: 'test-row',
              category: '应收票据',
              itemName: 'test',
              priorUnadjusted: C,
              priorAje: D,
              priorRje: E,
              priorAudited: 0, // will be computed
              ociImpairment: 0,
              periodIncrease: H,
              periodDecrease: I,
              endBalance: 0, // will be computed
              entityReclass: K,
              endUnadjusted: 0, // will be computed
              endAje: M,
              endRje: N,
              endAudited: 0, // will be computed
              endOciImpairment: 0,
              remark: '',
            }

            const result = recalcRow(row)

            // F = C + D + E
            const expectedF = C + D + E
            expect(result.priorAudited).toBeCloseTo(expectedF, 5)

            // J = F + H - I
            const expectedJ = expectedF + H - I
            expect(result.endBalance).toBeCloseTo(expectedJ, 5)

            // L = J + K
            const expectedL = expectedJ + K
            expect(result.endUnadjusted).toBeCloseTo(expectedL, 5)

            // O = L + M + N
            const expectedO = expectedL + M + N
            expect(result.endAudited).toBeCloseTo(expectedO, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d5-receivables-financing, Property 7: 动态行添加保持结构不变量**
   *
   * For any 当前行列表（长度N≥0），createEmptyRow() 产生的新行
   * 所有数值字段为0/空串，rowId为非空字符串。
   *
   * **Validates: Requirements 4.5, 6.6, 7.2**
   */
  describe('Property 7: 动态行添加保持结构不变量', () => {
    it('createEmptyRow() has all numeric fields = 0, string fields = empty, rowId non-empty', () => {
      fc.assert(
        fc.property(
          fc.array(
            fc.record({
              category: fc.constantFrom('应收票据', '应收账款'),
              priorUnadjusted: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
              endAudited: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
            }),
            { minLength: 0, maxLength: 20 }
          ),
          (_existingRows) => {
            // Test that createEmptyRow() always produces a valid empty row
            const newRow = createEmptyRow()

            // rowId is non-empty string
            expect(typeof newRow.rowId).toBe('string')
            expect(newRow.rowId.length).toBeGreaterThan(0)

            // All numeric fields are 0
            expect(newRow.priorUnadjusted).toBe(0)
            expect(newRow.priorAje).toBe(0)
            expect(newRow.priorRje).toBe(0)
            expect(newRow.priorAudited).toBe(0)
            expect(newRow.ociImpairment).toBe(0)
            expect(newRow.periodIncrease).toBe(0)
            expect(newRow.periodDecrease).toBe(0)
            expect(newRow.endBalance).toBe(0)
            expect(newRow.entityReclass).toBe(0)
            expect(newRow.endUnadjusted).toBe(0)
            expect(newRow.endAje).toBe(0)
            expect(newRow.endRje).toBe(0)
            expect(newRow.endAudited).toBe(0)
            expect(newRow.endOciImpairment).toBe(0)

            // All string fields are empty
            expect(newRow.category).toBe('')
            expect(newRow.itemName).toBe('')
            expect(newRow.remark).toBe('')
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
