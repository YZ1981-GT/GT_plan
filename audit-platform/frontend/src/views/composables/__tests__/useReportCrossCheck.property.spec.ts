/**
 * useReportCrossCheck — Property 24 (part 2): Consolidation Compute Identity under canonical resolution
 *
 * **Validates: Requirements 19.2, 19.5, 19.7**
 *
 * ACNR consumer wiring, task 28.5 — P24 compute-fidelity for the report cross-check.
 * Task 28.2 added an ACNR REPORT-domain `reportCodeMap` canonical `row_code → row_name`
 * resolution step to `computeCrossCheckResults`. The migration must be **non-destructive**:
 * when the same report values are resolvable under BOTH the canonical `row_code` key and the
 * `row_name` key, adding `reportCodeMap` must NOT change any of the 7 cross-check equation
 * outcomes (the results computed migrated-vs-pre-migration are byte-identical).
 *
 * This is the "计算结果与迁移前一致" clause of P24: canonical resolution and the legacy
 * exact/fuzzy path converge whenever both can resolve.
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { computeCrossCheckResults, type CrossCheckItem } from '../useReportCrossCheck'

// Canonical alias codes that `computeCrossCheckResults.get()` probes first (exact pass),
// paired with the Chinese row_name and a realistic report row_code.
const BS_FIGURES = [
  { alias: 'assets_total', name: '资产总计', code: 'BS-031' },
  { alias: 'liabilities_total', name: '负债合计', code: 'BS-055' },
  { alias: 'equity_total', name: '所有者权益合计', code: 'BS-078' },
  { alias: 'BS-001', name: '货币资金', code: 'BS-001' },
] as const

const IS_FIGURES = [
  { alias: 'IS-001', name: '营业收入', code: 'IS-001' },
  { alias: 'IS-002', name: '营业成本', code: 'IS-002' },
  { alias: 'IS-017', name: '利润总额', code: 'IS-017' },
  { alias: 'IS-018', name: '所得税费用', code: 'IS-018' },
  { alias: 'IS-019', name: '净利润', code: 'IS-019' },
] as const

/** Serialize the 7 CrossCheckItem results into a comparable, deterministic shape. */
function serialize(items: CrossCheckItem[]): string {
  return JSON.stringify(
    items.map((i) => [i.description, i.leftValue, i.rightValue, i.diff, i.passed]),
  )
}

describe('computeCrossCheckResults — P24 compute identity (property)', () => {
  it('adding canonical reportCodeMap does NOT change results when values resolve under both code+name keys', () => {
    fc.assert(
      fc.property(
        fc.record({
          assetsTotal: fc.integer({ min: 1, max: 100000 }),
          liabilitiesTotal: fc.integer({ min: 1, max: 50000 }),
          equityTotal: fc.integer({ min: 1, max: 50000 }),
          cash: fc.integer({ min: 1, max: 30000 }),
          revenue: fc.integer({ min: 1, max: 100000 }),
          cost: fc.integer({ min: 1, max: 50000 }),
          profitBeforeTax: fc.integer({ min: 1, max: 50000 }),
          incomeTax: fc.integer({ min: 1, max: 20000 }),
          netProfit: fc.integer({ min: 1, max: 30000 }),
        }),
        (v) => {
          const bsVals = [v.assetsTotal, v.liabilitiesTotal, v.equityTotal, v.cash]
          const isVals = [v.revenue, v.cost, v.profitBeforeTax, v.incomeTax, v.netProfit]

          // Value tables keyed under BOTH the canonical row_code AND the row_name,
          // so the same value is resolvable via either lookup path.
          const bsMap: Record<string, number> = {}
          BS_FIGURES.forEach((f, i) => {
            bsMap[f.alias] = bsVals[i]
            bsMap[f.name] = bsVals[i]
            bsMap[f.code] = bsVals[i]
          })
          const isMap: Record<string, number> = {}
          IS_FIGURES.forEach((f, i) => {
            isMap[f.alias] = isVals[i]
            isMap[f.name] = isVals[i]
            isMap[f.code] = isVals[i]
          })

          // Canonical REPORT-domain registry: row_code → row_name (ACNR-backed).
          const reportCodeMap: Record<string, string> = {}
          for (const f of [...BS_FIGURES, ...IS_FIGURES]) reportCodeMap[f.code] = f.name

          // Pre-migration (no registry) vs migrated (with canonical reportCodeMap).
          const legacy = computeCrossCheckResults({ bsMap, isMap })
          const migrated = computeCrossCheckResults({ bsMap, isMap, reportCodeMap })

          expect(migrated).toHaveLength(7)
          expect(legacy).toHaveLength(7)
          // 计算结果与迁移前一致 — byte-identical 7-equation outcomes.
          expect(serialize(migrated)).toBe(serialize(legacy))
        },
      ),
      { numRuns: 60 },
    )
  })

  it('canonical-only value table: reportCodeMap resolves what fuzzy cannot (divergence sanity check)', () => {
    // When values are keyed ONLY by opaque row_code (no name/alias key), the legacy path
    // cannot resolve (→ 0/null) but the canonical registry path can. This confirms the
    // registry pass is actually exercised (i.e. the identity property above is meaningful,
    // not vacuous because everything trivially resolves the same way).
    fc.assert(
      fc.property(
        fc.record({
          assetsTotal: fc.integer({ min: 1, max: 100000 }),
          liabilitiesTotal: fc.integer({ min: 1, max: 50000 }),
          equityTotal: fc.integer({ min: 1, max: 50000 }),
        }),
        (v) => {
          const bsMap: Record<string, number> = {
            'BS-031': v.assetsTotal,
            'BS-055': v.liabilitiesTotal,
            'BS-078': v.equityTotal,
          }
          const reportCodeMap: Record<string, string> = {
            'BS-031': '资产总计',
            'BS-055': '负债合计',
            'BS-078': '所有者权益合计',
          }
          const legacy = computeCrossCheckResults({ bsMap, isMap: {} })
          const migrated = computeCrossCheckResults({ bsMap, isMap: {}, reportCodeMap })

          // Legacy cannot resolve opaque codes → totalAssets null.
          expect(legacy[0].leftValue).toBeNull()
          // Canonical registry resolves BS-031 → 资产总计 → value.
          expect(migrated[0].leftValue).toBe(v.assetsTotal)
        },
      ),
      { numRuns: 40 },
    )
  })
})
