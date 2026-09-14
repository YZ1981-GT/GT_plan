/**
 * useD5CrossSheet PBT — Property 5: 跨sheet按类别聚合正确性
 *
 * Feature: d5-receivables-financing, Property 5: 跨sheet按类别聚合正确性
 * Generator: custom DetailRow[] generator (category randomly '应收票据'/'应收账款')
 * Assertion: SUM by category === manual filter+reduce result
 * Use parseNum from useD5FormulaEngine
 *
 * **Validates: Requirements 3.1, 4.4**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import { useD5CrossSheet } from '../composables/useD5CrossSheet'
import type { ChecklistResponse } from '../composables/useD5FormData'
import { parseNum } from '../composables/useD5FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

const categoryArb = fc.constantFrom('应收票据', '应收账款')

const detailRowArb = fc.record({
  rowId: fc.uuid().map(u => `row-${u}`),
  category: categoryArb,
  itemName: fc.string({ minLength: 0, maxLength: 10 }),
  priorUnadjusted: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorAje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorRje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  priorAudited: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  ociImpairment: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  periodIncrease: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  periodDecrease: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endBalance: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  entityReclass: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endUnadjusted: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endAje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endRje: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endAudited: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  endOciImpairment: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  remark: fc.string({ minLength: 0, maxLength: 10 }),
})

const detailRowsArb = fc.array(detailRowArb, { minLength: 0, maxLength: 20 })

// ─── Property-Based Test ─────────────────────────────────────────────────────

describe('useD5CrossSheet - Property-Based Tests', () => {
  /**
   * **Feature: d5-receivables-financing, Property 5: 跨sheet按类别聚合正确性**
   *
   * For any 明细表D5-2行数据集，按"类别"列(应收票据/应收账款)分组后，每组的
   * endAudited之和应等于审定表D5-1对应行的期末审定值。
   * 即 SUM(rows.filter(r => r.category === cat).map(r => r.endAudited)) 等于
   * 审定表对应行值。
   *
   * **Validates: Requirements 3.1, 4.4**
   */
  describe('Property 5: 跨sheet按类别聚合正确性', () => {
    it('categoryAggregation matches manual filter+reduce for endAudited and priorAudited', () => {
      fc.assert(
        fc.property(
          detailRowsArb,
          (rows) => {
            // Build the allResponses Map with D5-2-rows remark containing JSON
            const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
            allResponses.value.set('D5-2-rows', {
              item_id: 'D5-2-rows',
              conclusion: null,
              remark: JSON.stringify(rows),
            })

            // Call useD5CrossSheet
            const { categoryAggregation } = useD5CrossSheet({ allResponses })

            // Manual calculation
            const notesRows = rows.filter(r => r.category === '应收票据')
            const accountsRows = rows.filter(r => r.category === '应收账款')

            const expectedNotesCurrent = notesRows.reduce((sum, r) => sum + parseNum(r.endAudited), 0)
            const expectedNotesPrior = notesRows.reduce((sum, r) => sum + parseNum(r.priorAudited), 0)
            const expectedAccountsCurrent = accountsRows.reduce((sum, r) => sum + parseNum(r.endAudited), 0)
            const expectedAccountsPrior = accountsRows.reduce((sum, r) => sum + parseNum(r.priorAudited), 0)

            // Assert
            const agg = categoryAggregation.value
            expect(agg.notesReceivable.current).toBeCloseTo(expectedNotesCurrent, 5)
            expect(agg.notesReceivable.prior).toBeCloseTo(expectedNotesPrior, 5)
            expect(agg.accountsReceivable.current).toBeCloseTo(expectedAccountsCurrent, 5)
            expect(agg.accountsReceivable.prior).toBeCloseTo(expectedAccountsPrior, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
