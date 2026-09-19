/**
 * n1LossMigration.spec.ts — Property 7/8 (迁移纯函数)
 *
 * Spec: .kiro/specs/n1-loss-check-source-alignment/
 * Task: 2.4
 * Requirements: 9.1, 9.2
 *
 * Tests `migrateLegacyLossRows` for:
 * - Property 7: 历史迁移幂等
 * - Property 8: 迁移不猜测
 */
import { describe, it, expect, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import {
  migrateLegacyLossRows,
  _resetMigrationIdSeq,
  type LegacyLossRow,
} from '../composables/n1LossMigration'
import type { N1LossRow } from '../composables/useN1LossCheck'

// Reset ID sequence before each test for determinism
beforeEach(() => {
  _resetMigrationIdSeq(0)
})

// ─── Generators ─────────────────────────────────────────────────────────────

const arbLegacyRow: fc.Arbitrary<LegacyLossRow> = fc.record({
  lossYear: fc.integer({ min: 2010, max: 2030 }),
  maxYears: fc.integer({ min: 3, max: 10 }),
  lossAmount: fc.double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true }),
  recoveredBegin: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  currentRecovery: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  futureTaxableIncome: fc.double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true }),
  taxRate: fc.oneof(
    fc.constant(0.25),
    fc.constant(0.15),
    fc.double({ min: 0.05, max: 0.50, noNaN: true, noDefaultInfinity: true }),
  ),
  recognitionBasis: fc.oneof(
    fc.constant(''),
    fc.constant('有充足的应纳税所得额'),
    fc.string({ minLength: 0, maxLength: 50 }),
  ),
})

const arbAuditYear = fc.integer({ min: 2020, max: 2035 })

// ─── Property 7: 历史迁移幂等 ──────────────────────────────────────────────

describe('Property 7: migrateLegacyLossRows is idempotent', () => {
  /**
   * **Validates: Requirements 6.2, 6.4**
   *
   * migrateLegacyLossRows(legacy, y, migrateLegacyLossRows(legacy, y, []).rows)
   * → added === 0 and rows are field-equal to first pass.
   */
  it('second pass with first pass result as existing → added === 0', () => {
    fc.assert(
      fc.property(
        fc.array(arbLegacyRow, { minLength: 1, maxLength: 10 }),
        arbAuditYear,
        (legacy, auditYear) => {
          _resetMigrationIdSeq(0)
          const firstPass = migrateLegacyLossRows(legacy, auditYear, [])

          _resetMigrationIdSeq(100) // different id seq to ensure dedup is by expiryYear not id
          const secondPass = migrateLegacyLossRows(legacy, auditYear, firstPass.rows)

          expect(secondPass.added).toBe(0)
          // rows should be same length (no duplicates added)
          expect(secondPass.rows.length).toBe(firstPass.rows.length)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('first pass rows are field-equal to second pass rows (ignoring id)', () => {
    fc.assert(
      fc.property(
        fc.array(arbLegacyRow, { minLength: 1, maxLength: 8 }),
        arbAuditYear,
        (legacy, auditYear) => {
          _resetMigrationIdSeq(0)
          const firstPass = migrateLegacyLossRows(legacy, auditYear, [])

          _resetMigrationIdSeq(200)
          const secondPass = migrateLegacyLossRows(legacy, auditYear, firstPass.rows)

          // Compare rows ignoring id (second pass uses existing rows unchanged)
          for (let i = 0; i < firstPass.rows.length; i++) {
            const a = { ...firstPass.rows[i], id: '' }
            const b = { ...secondPass.rows[i], id: '' }
            expect(a).toEqual(b)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('deduplication is by expiryYear (same year legacy rows → only first added)', () => {
    const sameLossYear = 2020
    const maxYears = 5
    const legacy: LegacyLossRow[] = [
      { lossYear: sameLossYear, maxYears, lossAmount: 100000 },
      { lossYear: sameLossYear, maxYears, lossAmount: 200000 }, // same expiryYear
    ]

    _resetMigrationIdSeq(0)
    const result = migrateLegacyLossRows(legacy, 2026, [])
    // Only 1 row added (second is skipped because same expiryYear=2025)
    expect(result.added).toBe(1)
    expect(result.skipped).toBe(1)
    expect(result.rows.length).toBe(1)
    expect(result.rows[0].expiryYear).toBe(sameLossYear + maxYears)
  })
})

// ─── Property 8: 迁移不猜测 ────────────────────────────────────────────────

describe('Property 8: migration does not guess unknown fields', () => {
  /**
   * **Validates: Requirements 6.3**
   *
   * 迁移产出的每一行:
   * - priorUnrecognized === 0
   * - sufficient === ''
   * - sourceOperating === false
   * - sourceTemporaryDiff === false
   * - sourceOther === false
   * - indexRef === ''
   * - auditAdjustment === 0
   */
  it('all migrated rows have priorUnrecognized=0, sufficient="", sources=false, indexRef="", auditAdjustment=0', () => {
    fc.assert(
      fc.property(
        fc.array(arbLegacyRow, { minLength: 1, maxLength: 15 }),
        arbAuditYear,
        (legacy, auditYear) => {
          _resetMigrationIdSeq(0)
          const result = migrateLegacyLossRows(legacy, auditYear, [])

          for (const row of result.rows) {
            expect(row.priorUnrecognized).toBe(0)
            expect(row.sufficient).toBe('')
            expect(row.sourceOperating).toBe(false)
            expect(row.sourceTemporaryDiff).toBe(false)
            expect(row.sourceOther).toBe(false)
            expect(row.indexRef).toBe('')
            expect(row.auditAdjustment).toBe(0)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  it('recognizedAmount for expired rows is 0', () => {
    fc.assert(
      fc.property(
        arbLegacyRow,
        (legacy) => {
          // Force expired: auditYear > expiryYear
          const lossYear = Number(legacy.lossYear) || 2015
          const maxYears = Number(legacy.maxYears) || 5
          const expiryYear = lossYear + maxYears
          const auditYear = expiryYear + 2 // expired

          _resetMigrationIdSeq(0)
          const result = migrateLegacyLossRows([legacy], auditYear, [])
          if (result.rows.length > 0) {
            expect(result.rows[0].recognizedAmount).toBe(0)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('taxRate defaults to 0.25 when legacy taxRate is falsy', () => {
    const legacy: LegacyLossRow[] = [
      { lossYear: 2020, maxYears: 5, lossAmount: 100000, taxRate: 0 },
      { lossYear: 2021, maxYears: 5, lossAmount: 50000, taxRate: null },
    ]

    _resetMigrationIdSeq(0)
    const result = migrateLegacyLossRows(legacy, 2024, [])
    for (const row of result.rows) {
      expect(row.taxRate).toBe(0.25)
    }
  })
})
