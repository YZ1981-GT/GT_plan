/**
 * n1UnrecognizedLossPayload.spec.ts — Property 5/6/9
 *
 * Spec: .kiro/specs/n1-loss-check-source-alignment/
 * Task: 2.4
 * Requirements: 9.1, 9.2
 *
 * Tests `deriveUnrecognizedLossPayload` from `useN1DisclosureSource.ts`:
 * - Property 5: totalUnrecognized === round2(Σ unrecognizedAmount per row)
 * - Property 6: 同一 expiryYear 多行聚合后条数为1，聚合前后总额相等
 * - Property 9: N1-5-rows 缺失或空数组 ⇒ hasData===false ∧ rows.length===0
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { deriveUnrecognizedLossPayload } from '../composables/useN1DisclosureSource'

// ─── Helpers ────────────────────────────────────────────────────────────────

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

/** Build a minimal N1LossRow-like object for the payload derivation */
function buildRawRow(overrides: Partial<{
  expiryYear: number
  bookAmount: number
  auditAdjustment: number
  recognizedAmount: number
  priorUnrecognized: number
  basis: string
}> = {}) {
  return {
    expiryYear: overrides.expiryYear ?? 2028,
    bookAmount: overrides.bookAmount ?? 100000,
    auditAdjustment: overrides.auditAdjustment ?? 0,
    recognizedAmount: overrides.recognizedAmount ?? 50000,
    priorUnrecognized: overrides.priorUnrecognized ?? 0,
    basis: overrides.basis ?? '',
    // other fields not used by payload derivation
    taxRate: 0.25,
    sufficient: '',
    sourceOperating: false,
    sourceTemporaryDiff: false,
    sourceOther: false,
    indexRef: '',
    id: 'loss-1',
  }
}

/** Build allResponses Map with N1-5-rows key */
function buildResponses(rows: any[]): Map<string, any> {
  const map = new Map<string, any>()
  map.set('N1-5-rows', { conclusion: JSON.stringify(rows) })
  return map
}

// ─── Generators ─────────────────────────────────────────────────────────────

const arbYear = fc.integer({ min: 2020, max: 2040 })
const arbAmount = fc.double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true })
const arbSmallAmount = fc.double({ min: -1e5, max: 1e5, noNaN: true, noDefaultInfinity: true })

const arbRawRow = fc.record({
  expiryYear: arbYear,
  bookAmount: arbAmount,
  auditAdjustment: arbSmallAmount,
  recognizedAmount: arbAmount,
  priorUnrecognized: arbAmount,
  basis: fc.oneof(fc.constant(''), fc.string({ minLength: 1, maxLength: 30 })),
}).map((r) => buildRawRow(r))

// ─── Property 5: totalUnrecognized === round2(Σ unrecognizedAmount) ──────────

describe('Property 5: totalUnrecognized === round2(Σ unrecognizedAmount per input row)', () => {
  /**
   * **Validates: Requirements 4.1, 4.3**
   */
  it('total equals sum of per-row max(0, audited - recognized)', () => {
    fc.assert(
      fc.property(
        fc.array(arbRawRow, { minLength: 1, maxLength: 20 }),
        (rawRows) => {
          const allResponses = buildResponses(rawRows)
          const payload = deriveUnrecognizedLossPayload(allResponses)

          // Manually compute expected total
          let expectedTotal = 0
          for (const row of rawRows) {
            const audited = round2(row.bookAmount + row.auditAdjustment)
            const unrecognized = Math.max(0, round2(audited - row.recognizedAmount))
            expectedTotal += unrecognized
          }
          expectedTotal = round2(expectedTotal)

          expect(payload.totalUnrecognized).toBeCloseTo(expectedTotal, 1)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('totalUnrecognized equals sum of payload.rows[].unrecognized', () => {
    fc.assert(
      fc.property(
        fc.array(arbRawRow, { minLength: 1, maxLength: 15 }),
        (rawRows) => {
          const allResponses = buildResponses(rawRows)
          const payload = deriveUnrecognizedLossPayload(allResponses)

          const sumFromPayloadRows = round2(
            payload.rows.reduce((s, r) => s + r.unrecognized, 0),
          )
          expect(payload.totalUnrecognized).toBeCloseTo(sumFromPayloadRows, 1)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── Property 6: 同一 expiryYear 聚合 ──────────────────────────────────────

describe('Property 6: same expiryYear rows aggregate to 1 entry, totals preserved', () => {
  /**
   * **Validates: Requirements 4.1, 4.3**
   */
  it('grouped by expiryYear, each year appears once in payload.rows', () => {
    fc.assert(
      fc.property(
        fc.array(arbRawRow, { minLength: 2, maxLength: 15 }),
        (rawRows) => {
          const allResponses = buildResponses(rawRows)
          const payload = deriveUnrecognizedLossPayload(allResponses)

          // Each expiryYear should appear at most once
          const years = payload.rows.map((r) => r.expiryYear)
          const unique = new Set(years)
          expect(unique.size).toBe(years.length)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('aggregation of same-year rows: unrecognized equals sum of individual rows for that year', () => {
    // Construct input with guaranteed duplicate years
    fc.assert(
      fc.property(
        arbYear,
        fc.array(arbAmount, { minLength: 2, maxLength: 5 }),
        fc.array(arbSmallAmount, { minLength: 2, maxLength: 5 }),
        fc.array(arbAmount, { minLength: 2, maxLength: 5 }),
        (year, books, adjs, recognizeds) => {
          const len = Math.min(books.length, adjs.length, recognizeds.length)
          const rawRows = Array.from({ length: len }, (_, i) =>
            buildRawRow({
              expiryYear: year, // all same year
              bookAmount: books[i],
              auditAdjustment: adjs[i],
              recognizedAmount: recognizeds[i],
            }),
          )

          const allResponses = buildResponses(rawRows)
          const payload = deriveUnrecognizedLossPayload(allResponses)

          // Should produce exactly 1 row for this year
          const yearRows = payload.rows.filter((r) => r.expiryYear === String(year))
          expect(yearRows.length).toBe(1)

          // Sum check
          let expectedUnrecognized = 0
          for (const row of rawRows) {
            const audited = round2(row.bookAmount + row.auditAdjustment)
            expectedUnrecognized += Math.max(0, round2(audited - row.recognizedAmount))
          }
          expectedUnrecognized = round2(expectedUnrecognized)

          expect(yearRows[0].unrecognized).toBeCloseTo(expectedUnrecognized, 1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('total before and after aggregation is the same', () => {
    fc.assert(
      fc.property(
        fc.array(arbRawRow, { minLength: 1, maxLength: 15 }),
        (rawRows) => {
          const allResponses = buildResponses(rawRows)
          const payload = deriveUnrecognizedLossPayload(allResponses)

          // Pre-aggregation total
          let preAggTotal = 0
          for (const row of rawRows) {
            const audited = round2(row.bookAmount + row.auditAdjustment)
            preAggTotal += Math.max(0, round2(audited - row.recognizedAmount))
          }
          preAggTotal = round2(preAggTotal)

          // Post-aggregation total (from payload)
          expect(payload.totalUnrecognized).toBeCloseTo(preAggTotal, 1)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── Property 9: 无数据时 hasData===false ───────────────────────────────────

describe('Property 9: missing or empty N1-5-rows ⇒ hasData===false ∧ rows.length===0', () => {
  /**
   * **Validates: Requirements 4.4**
   */
  it('key missing from allResponses', () => {
    const allResponses = new Map<string, any>()
    const payload = deriveUnrecognizedLossPayload(allResponses)
    expect(payload.hasData).toBe(false)
    expect(payload.rows.length).toBe(0)
  })

  it('key present but conclusion is empty array JSON', () => {
    const allResponses = new Map<string, any>()
    allResponses.set('N1-5-rows', { conclusion: '[]' })
    const payload = deriveUnrecognizedLossPayload(allResponses)
    expect(payload.hasData).toBe(false)
    expect(payload.rows.length).toBe(0)
  })

  it('key present but conclusion is null', () => {
    const allResponses = new Map<string, any>()
    allResponses.set('N1-5-rows', { conclusion: null })
    const payload = deriveUnrecognizedLossPayload(allResponses)
    expect(payload.hasData).toBe(false)
    expect(payload.rows.length).toBe(0)
  })

  it('key present but conclusion is invalid JSON', () => {
    const allResponses = new Map<string, any>()
    allResponses.set('N1-5-rows', { conclusion: '{broken json' })
    const payload = deriveUnrecognizedLossPayload(allResponses)
    expect(payload.hasData).toBe(false)
    expect(payload.rows.length).toBe(0)
  })

  it('key present but conclusion is not an array', () => {
    const allResponses = new Map<string, any>()
    allResponses.set('N1-5-rows', { conclusion: '{"foo":1}' })
    const payload = deriveUnrecognizedLossPayload(allResponses)
    expect(payload.hasData).toBe(false)
    expect(payload.rows.length).toBe(0)
  })

  it('with valid rows, hasData is true', () => {
    fc.assert(
      fc.property(
        fc.array(arbRawRow, { minLength: 1, maxLength: 5 }),
        (rawRows) => {
          const allResponses = buildResponses(rawRows)
          const payload = deriveUnrecognizedLossPayload(allResponses)
          expect(payload.hasData).toBe(true)
          expect(payload.rows.length).toBeGreaterThan(0)
        },
      ),
      { numRuns: 50 },
    )
  })
})
