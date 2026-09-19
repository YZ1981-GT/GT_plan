/**
 * Property-Based Tests — D4 营业收入跨Sheet聚合
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 4.2
 *
 * Property 5: 跨Sheet聚合正确性（D4-2/D4-3→D4-1）
 *
 * **Validates: Requirements 2.4, 2.6, 2.7, 17.1, 17.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import { useD4CrossSheet } from '../useD4CrossSheet'
import type { ChecklistResponse, ProjectContext } from '../useD4FormData'

// ─── Helpers ────────────────────────────────────────────────────────────────

/**
 * Build a reactive allResponses Map with D4-2-rows data for testing
 */
function buildAllResponses(d4Row2Data: any[], d4Row3Data: any[] = []) {
  const map = new Map<string, ChecklistResponse>()
  if (d4Row2Data.length > 0) {
    map.set('D4-2-rows', {
      item_id: 'D4-2-rows',
      conclusion: null,
      remark: JSON.stringify(d4Row2Data),
    })
  }
  if (d4Row3Data.length > 0) {
    map.set('D4-3-rows', {
      item_id: 'D4-3-rows',
      conclusion: null,
      remark: JSON.stringify(d4Row3Data),
    })
  }
  return ref(map)
}

// ─── Property 5 PBT: 跨Sheet聚合正确性 ─────────────────────────────────────

describe('Feature: d4-operating-revenue, Property 5: 跨Sheet聚合正确性', () => {
  /**
   * **Validates: Requirements 2.4, 2.6, 2.7, 17.1, 17.2**
   *
   * For any D4-2 row dataset grouped by product, the sum of each group's
   * audited value (SUM(months) + auditAdjustment) should equal
   * mainRevenueByProduct[product].current.
   *
   * And mainRevenueTotal.current should equal the sum of all products.
   *
   * Similarly for D4-3 → D4-1 other section.
   * And grandTotal = mainRevenueTotal + otherRevenueTotal.
   */

  const productArb = fc.constantFrom('产品A', '产品B', '产品C', '产品D')
  const monthValArb = fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true })
  const adjArb = fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true })

  const d4Row2Arb = fc.record({
    rowId: fc.uuid(),
    product: productArb,
    months: fc.array(monthValArb, { minLength: 12, maxLength: 12 }),
    auditAdjustment: adjArb,
    priorUnadjusted: adjArb,
    priorAdjustment: adjArb,
  })

  it('mainRevenueByProduct aggregation matches manual groupBy sum', () => {
    fc.assert(
      fc.property(
        fc.array(d4Row2Arb, { minLength: 1, maxLength: 20 }),
        (rows) => {
          const allResponses = buildAllResponses(rows)
          const projectContext = ref<ProjectContext>({})

          const { mainRevenueByProduct } = useD4CrossSheet({ allResponses, projectContext })

          // Manually compute expected groupBy sums
          const expectedByProduct: Record<string, { current: number; prior: number }> = {}
          for (const row of rows) {
            const product = row.product || '未命名'
            const monthsTotal = row.months.reduce((a, b) => a + b, 0)
            const audited = monthsTotal + row.auditAdjustment
            const priorAudited = row.priorUnadjusted + row.priorAdjustment

            if (!expectedByProduct[product]) {
              expectedByProduct[product] = { current: 0, prior: 0 }
            }
            expectedByProduct[product].current += audited
            expectedByProduct[product].prior += priorAudited
          }

          const actual = mainRevenueByProduct.value

          // Verify all products match
          const actualProducts = Object.keys(actual).sort()
          const expectedProducts = Object.keys(expectedByProduct).sort()
          expect(actualProducts).toEqual(expectedProducts)

          for (const product of expectedProducts) {
            expect(actual[product].current).toBeCloseTo(expectedByProduct[product].current, 5)
            expect(actual[product].prior).toBeCloseTo(expectedByProduct[product].prior, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('mainRevenueTotal.current equals sum of all rows audited values', () => {
    fc.assert(
      fc.property(
        fc.array(d4Row2Arb, { minLength: 1, maxLength: 20 }),
        (rows) => {
          const allResponses = buildAllResponses(rows)
          const projectContext = ref<ProjectContext>({})

          const { mainRevenueTotal } = useD4CrossSheet({ allResponses, projectContext })

          // Manually compute expected total
          let expectedCurrent = 0
          let expectedPrior = 0
          for (const row of rows) {
            const monthsTotal = row.months.reduce((a, b) => a + b, 0)
            expectedCurrent += monthsTotal + row.auditAdjustment
            expectedPrior += row.priorUnadjusted + row.priorAdjustment
          }

          expect(mainRevenueTotal.value.current).toBeCloseTo(expectedCurrent, 5)
          expect(mainRevenueTotal.value.prior).toBeCloseTo(expectedPrior, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('otherRevenueByItem aggregation matches manual groupBy sum (D4-3→D4-1)', () => {
    const itemArb = fc.constantFrom('租金收入', '利息收入', '咨询服务', '其他')
    const d4Row3Arb = fc.record({
      rowId: fc.uuid(),
      item: itemArb,
      currentUnadjusted: adjArb,
      currentAdjustment: adjArb,
      currentAudited: fc.constant(undefined as number | undefined),
      priorUnadjusted: adjArb,
      priorAdjustment: adjArb,
      priorAudited: fc.constant(undefined as number | undefined),
    })

    fc.assert(
      fc.property(
        fc.array(d4Row3Arb, { minLength: 1, maxLength: 15 }),
        (rows) => {
          const allResponses = buildAllResponses([], rows)
          const projectContext = ref<ProjectContext>({})

          const { otherRevenueByItem, otherRevenueTotal } = useD4CrossSheet({ allResponses, projectContext })

          // Manually compute expected groupBy sums
          const expectedByItem: Record<string, { current: number; prior: number }> = {}
          let expectedTotalCurrent = 0
          let expectedTotalPrior = 0

          for (const row of rows) {
            const item = row.item || '未命名'
            const currentAudited = row.currentUnadjusted + row.currentAdjustment
            const priorAudited = row.priorUnadjusted + row.priorAdjustment

            if (!expectedByItem[item]) {
              expectedByItem[item] = { current: 0, prior: 0 }
            }
            expectedByItem[item].current += currentAudited
            expectedByItem[item].prior += priorAudited
            expectedTotalCurrent += currentAudited
            expectedTotalPrior += priorAudited
          }

          const actualByItem = otherRevenueByItem.value

          // Verify all items match
          const actualItems = Object.keys(actualByItem).sort()
          const expectedItems = Object.keys(expectedByItem).sort()
          expect(actualItems).toEqual(expectedItems)

          for (const item of expectedItems) {
            expect(actualByItem[item].current).toBeCloseTo(expectedByItem[item].current, 5)
            expect(actualByItem[item].prior).toBeCloseTo(expectedByItem[item].prior, 5)
          }

          // Verify total
          expect(otherRevenueTotal.value.current).toBeCloseTo(expectedTotalCurrent, 5)
          expect(otherRevenueTotal.value.prior).toBeCloseTo(expectedTotalPrior, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('adjudicationForDisclosure.total equals mainRevenueTotal + otherRevenueTotal', () => {
    const itemArb = fc.constantFrom('租金收入', '利息收入', '咨询服务')
    const d4Row3Arb = fc.record({
      rowId: fc.uuid(),
      item: itemArb,
      currentUnadjusted: adjArb,
      currentAdjustment: adjArb,
      currentAudited: fc.constant(undefined as number | undefined),
      priorUnadjusted: adjArb,
      priorAdjustment: adjArb,
      priorAudited: fc.constant(undefined as number | undefined),
    })

    fc.assert(
      fc.property(
        fc.array(d4Row2Arb, { minLength: 1, maxLength: 10 }),
        fc.array(d4Row3Arb, { minLength: 1, maxLength: 10 }),
        (d4Rows2, d4Rows3) => {
          const allResponses = buildAllResponses(d4Rows2, d4Rows3)
          const projectContext = ref<ProjectContext>({})

          const { mainRevenueTotal, otherRevenueTotal, adjudicationForDisclosure } =
            useD4CrossSheet({ allResponses, projectContext })

          const expectedTotal = mainRevenueTotal.value.current + otherRevenueTotal.value.current

          expect(adjudicationForDisclosure.value.mainAudited).toBeCloseTo(mainRevenueTotal.value.current, 5)
          expect(adjudicationForDisclosure.value.otherAudited).toBeCloseTo(otherRevenueTotal.value.current, 5)
          expect(adjudicationForDisclosure.value.total).toBeCloseTo(expectedTotal, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})
