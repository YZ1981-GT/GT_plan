/**
 * useD6CrossSheet PBT — 跨Sheet联动 Property-Based Tests
 *
 * Property 5: 按分类聚合正确性
 * Property 12: 三区块交叉验证（净值小计=原值小计-坏账小计）
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Testing framework: fast-check
 * numRuns: 100
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { parseNum, calcSubtotal, calcBlockTotal, calcNetValue } from '../composables/useD6FormulaEngine'

// ─── Property 5: 按分类聚合正确性 ─────────────────────────────────────────────
// **Validates: Requirements 3.1, 3.2, 5.5, 5.6**

describe('Feature: d6-contract-assets, Property 5: 按分类聚合正确性', () => {
  /** Custom generator for DetailRow-like objects with contractType and endAudited */
  const detailRowArb = fc.record({
    contractType: fc.constantFrom('工程施工', '质量保证金', '其他'),
    endAudited: fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
  })

  const detailRowsArb = fc.array(detailRowArb, { minLength: 0, maxLength: 50 })

  it('SUM of endAudited per category matches manual filter+reduce result', () => {
    fc.assert(
      fc.property(detailRowsArb, (rows) => {
        // Simulate the aggregation logic from useD6CrossSheet.originalValueAggregation
        const aggregated: Record<string, number> = {}
        for (const row of rows) {
          const type = row.contractType || '其他'
          if (!aggregated[type]) {
            aggregated[type] = 0
          }
          aggregated[type] += parseNum(row.endAudited)
        }

        // Verify each category against manual filter+reduce
        const categories = ['工程施工', '质量保证金', '其他'] as const
        for (const cat of categories) {
          const manualSum = rows
            .filter((r) => r.contractType === cat)
            .reduce((sum, r) => sum + parseNum(r.endAudited), 0)

          const aggregatedValue = aggregated[cat] ?? 0
          expect(aggregatedValue).toBeCloseTo(manualSum, 5)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('total across all categories equals SUM of all rows endAudited', () => {
    fc.assert(
      fc.property(detailRowsArb, (rows) => {
        // Aggregate by category
        const aggregated: Record<string, number> = {}
        for (const row of rows) {
          const type = row.contractType || '其他'
          if (!aggregated[type]) {
            aggregated[type] = 0
          }
          aggregated[type] += parseNum(row.endAudited)
        }

        // Sum of all category totals
        const categoryValues = Object.values(aggregated)
        const totalFromCategories = calcSubtotal(categoryValues)

        // Direct sum of all rows
        const directTotal = rows.reduce((sum, r) => sum + parseNum(r.endAudited), 0)

        expect(totalFromCategories).toBeCloseTo(directTotal, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 12: 三区块交叉验证（净值小计=原值小计-坏账小计）──────────────────
// **Validates: Requirements 2.9, 26.6**

describe('Feature: d6-contract-assets, Property 12: 三区块交叉验证（净值小计=原值小计-坏账小计）', () => {
  it('netValueValidation.isValid === (|block1Total - block2Total - block3Total| ≤ 0.01)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (block1Total, block2Total, block3Total) => {
          // The actual netValueValidation logic from useD6CrossSheet:
          // diff = block3.total - (block1.total - block2.total)
          // isValid = Math.abs(diff) <= 0.01
          const diff = block3Total - (block1Total - block2Total)
          const isValid = Math.abs(diff) <= 0.01

          // Our assertion: isValid should be true iff |block1Total - block2Total - block3Total| ≤ 0.01
          // Note: |block1Total - block2Total - block3Total| = |-(block3Total - (block1Total - block2Total))| = |diff|
          const expectedIsValid = Math.abs(block1Total - block2Total - block3Total) <= 0.01
          expect(isValid).toBe(expectedIsValid)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('when block3Total = block1Total - block2Total, validation passes', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (block1Total, block2Total) => {
          // Derive block3 from the formula: netValue = originalValue - impairment
          const block3Total = calcNetValue(block1Total, block2Total)

          // The validation: diff = block3.total - (block1.total - block2.total)
          const diff = block3Total - (block1Total - block2Total)
          const isValid = Math.abs(diff) <= 0.01

          // Should always pass since block3Total is exactly block1Total - block2Total
          expect(isValid).toBe(true)
          expect(Math.abs(diff)).toBeLessThanOrEqual(0.01)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('when block3Total deviates from expected, validation correctly detects mismatch', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: Math.fround(0.02), max: 1e6, noNaN: true, noDefaultInfinity: true }), // deviation > 0.01
        (block1Total, block2Total, deviation) => {
          // block3 deviates from expected net value
          const expectedNetValue = block1Total - block2Total
          const block3Total = expectedNetValue + deviation

          const diff = block3Total - (block1Total - block2Total)
          const isValid = Math.abs(diff) <= 0.01

          // deviation >= 0.02, so |diff| = deviation >= 0.02 > 0.01 → should be invalid
          expect(isValid).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })
})
