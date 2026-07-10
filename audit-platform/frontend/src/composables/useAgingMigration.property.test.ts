/**
 * Property-Based Tests for useAgingMigration composable
 *
 * Feature: aging-config-enhancement
 *
 * Validates aging legacy-data migration invariants using fast-check:
 * - Property 8:  D2 legacy flat-to-nested migration preserves all values
 * - Property 9:  D3/F1 legacy key migration preserves values
 * - Property 10: Config change preserves existing segment data
 * - Property 11: Serialization produces exclusively nested format
 *
 * **Validates: Requirements 4.2, 4.3, 4.5, 5.3, 5.4, 10.2, 10.3, 10.4**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  D2_FLAT_TO_SEGMENT,
  D2_FLAT_KEYS,
  isLegacyD2Format,
  migrateD2FlatToNested,
  migrateD3F1Keys,
  remapAgingData,
  remapRowAgingData,
  stripLegacyFlatKeys,
} from './useAgingMigration'
import type { AgingSegment } from './useAgingConfig'

// ── Shared helpers / generators ───────────────────────────────────────────────

/** Arbitrary non-negative numeric aging value (integers + finite doubles). */
const numArb = fc.oneof(
  fc.integer({ min: 0, max: 1_000_000 }),
  fc.double({ min: 0, max: 1_000_000, noNaN: true, noDefaultInfinity: true }),
)

const ALL_FLAT_KEYS = Array.from(D2_FLAT_KEYS)

/** period → nested aging object field name */
const PERIOD_FIELD: Record<'prior' | 'current' | 'audited', string> = {
  prior: 'agingPrior',
  current: 'agingCurrent',
  audited: 'agingAudited',
}

/** THREE_YEAR segment keys (legacy D3/F1 fixed keys) */
const THREE_YEAR_KEYS = ['within1', 'y1to2', 'y2to3', 'over3']
/** FIVE_YEAR segment keys */
const FIVE_YEAR_KEYS = ['within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5']

/** Segment key pool used for overlap-rich config-change generation */
const KEY_POOL = ['within1', 'y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5', 'seg_a', 'seg_b']

const mkSegment = (key: string): AgingSegment => ({ key, label: key, dayFrom: 0, dayTo: null })

/** Arbitrary legacy D2 row: all 18 flat fields + a couple of non-aging fields. */
const legacyD2FlatRowArb = fc.record({
  rowId: fc.string({ minLength: 1, maxLength: 8 }),
  seq: fc.integer({ min: 1, max: 999 }),
  customerName: fc.string({ maxLength: 12 }),
  ...Object.fromEntries(ALL_FLAT_KEYS.map((k) => [k, numArb])),
})

/** Arbitrary D3/F1 legacy row with the fixed {within1,y1to2,y2to3,over3} keys. */
const legacyD3F1RowArb = fc.record({
  rowId: fc.string({ minLength: 1, maxLength: 8 }),
  customerName: fc.string({ maxLength: 12 }),
  agingPrior: fc.record(Object.fromEntries(THREE_YEAR_KEYS.map((k) => [k, numArb]))),
  agingAudited: fc.record(Object.fromEntries(THREE_YEAR_KEYS.map((k) => [k, numArb]))),
})

/** Arbitrary aging-data dict keyed by a subset of the key pool. */
const agingDataArb = fc.dictionary(fc.constantFrom(...KEY_POOL), numArb, { maxKeys: KEY_POOL.length })

/** Arbitrary unique segment list drawn from the key pool (2-8 segments). */
const segmentsArb = fc
  .uniqueArray(fc.constantFrom(...KEY_POOL), { minLength: 2, maxLength: KEY_POOL.length })
  .map((keys) => keys.map(mkSegment))

// ══════════════════════════════════════════════════════════════════════════════
// Property 8: D2 legacy flat-to-nested migration preserves all values
// ══════════════════════════════════════════════════════════════════════════════

describe('useAgingMigration — Property 8: D2 legacy flat-to-nested migration preserves all values', () => {
  it('every flat value is preserved at the corresponding segment key with no loss', () => {
    // Feature: aging-config-enhancement, Property 8: D2 legacy flat-to-nested migration preserves all values
    // **Validates: Requirements 4.3, 10.2, 10.3**
    fc.assert(
      fc.property(legacyD2FlatRowArb, (raw) => {
        const migrated = migrateD2FlatToNested(raw)

        // Each flat field's value lands at nested[period][segmentKey]
        for (const [flatKey, mapping] of Object.entries(D2_FLAT_TO_SEGMENT)) {
          const field = PERIOD_FIELD[mapping.period]
          expect(migrated[field][mapping.segmentKey]).toBe(raw[flatKey])
        }
      }),
    )
  })

  it('produces exactly 6 keys per period (no duplication, no loss)', () => {
    // Feature: aging-config-enhancement, Property 8: D2 legacy flat-to-nested migration preserves all values
    // **Validates: Requirements 4.3, 10.2, 10.3**
    fc.assert(
      fc.property(legacyD2FlatRowArb, (raw) => {
        const migrated = migrateD2FlatToNested(raw)
        expect(Object.keys(migrated.agingPrior).sort()).toEqual([...FIVE_YEAR_KEYS].sort())
        expect(Object.keys(migrated.agingCurrent).sort()).toEqual([...FIVE_YEAR_KEYS].sort())
        expect(Object.keys(migrated.agingAudited).sort()).toEqual([...FIVE_YEAR_KEYS].sort())
      }),
    )
  })

  it('preserves non-aging fields and detects the legacy format', () => {
    // Feature: aging-config-enhancement, Property 8: D2 legacy flat-to-nested migration preserves all values
    // **Validates: Requirements 4.3, 10.2, 10.3**
    fc.assert(
      fc.property(legacyD2FlatRowArb, (raw) => {
        expect(isLegacyD2Format(raw)).toBe(true)
        const migrated = migrateD2FlatToNested(raw)
        expect(migrated.rowId).toBe(raw.rowId)
        expect(migrated.seq).toBe(raw.seq)
        expect(migrated.customerName).toBe(raw.customerName)
      }),
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 9: D3/F1 legacy key migration preserves values
// ══════════════════════════════════════════════════════════════════════════════

describe('useAgingMigration — Property 9: D3/F1 legacy key migration preserves values', () => {
  it('same-key config preserves every value (THREE_YEAR round-trip)', () => {
    // Feature: aging-config-enhancement, Property 9: D3/F1 legacy key migration preserves values
    // **Validates: Requirements 5.3, 5.4**
    const segments = THREE_YEAR_KEYS.map(mkSegment)
    fc.assert(
      fc.property(legacyD3F1RowArb, (raw) => {
        const migrated = migrateD3F1Keys(raw, segments)
        for (const key of THREE_YEAR_KEYS) {
          expect(migrated.agingPrior[key]).toBe(raw.agingPrior[key])
          expect(migrated.agingAudited[key]).toBe(raw.agingAudited[key])
        }
        // No agingCurrent for 2-period subjects
        expect(migrated.agingCurrent).toBeUndefined()
      }),
    )
  })

  it('config expansion keeps matched keys, zero-inits new keys, drops removed keys', () => {
    // Feature: aging-config-enhancement, Property 9: D3/F1 legacy key migration preserves values
    // **Validates: Requirements 5.3, 5.4**
    const newSegments = FIVE_YEAR_KEYS.map(mkSegment) // over3 dropped; y3to4/y4to5/over5 added
    fc.assert(
      fc.property(legacyD3F1RowArb, (raw) => {
        const migrated = migrateD3F1Keys(raw, newSegments)
        // Matched keys retained
        for (const key of ['within1', 'y1to2', 'y2to3']) {
          expect(migrated.agingPrior[key]).toBe(raw.agingPrior[key])
          expect(migrated.agingAudited[key]).toBe(raw.agingAudited[key])
        }
        // Newly added keys zero-initialized
        for (const key of ['y3to4', 'y4to5', 'over5']) {
          expect(migrated.agingPrior[key]).toBe(0)
          expect(migrated.agingAudited[key]).toBe(0)
        }
        // Removed key (over3) absent from result
        expect('over3' in migrated.agingPrior).toBe(false)
        expect('over3' in migrated.agingAudited).toBe(false)
        // Output keys exactly match new segment set
        expect(Object.keys(migrated.agingPrior).sort()).toEqual([...FIVE_YEAR_KEYS].sort())
      }),
    )
  })

  it('preserves non-aging fields', () => {
    // Feature: aging-config-enhancement, Property 9: D3/F1 legacy key migration preserves values
    // **Validates: Requirements 5.3, 5.4**
    const segments = THREE_YEAR_KEYS.map(mkSegment)
    fc.assert(
      fc.property(legacyD3F1RowArb, (raw) => {
        const migrated = migrateD3F1Keys(raw, segments)
        expect(migrated.rowId).toBe(raw.rowId)
        expect(migrated.customerName).toBe(raw.customerName)
      }),
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 10: Config change preserves existing segment data
// ══════════════════════════════════════════════════════════════════════════════

describe('useAgingMigration — Property 10: Config change preserves existing segment data', () => {
  it('remapAgingData keeps common-segment values and zero-inits new segments', () => {
    // Feature: aging-config-enhancement, Property 10: Config change preserves existing segment data
    // **Validates: Requirements 4.5**
    fc.assert(
      fc.property(agingDataArb, segmentsArb, (oldData, newSegments) => {
        const result = remapAgingData(oldData, newSegments)

        // (result keys) === (new segment keys) exactly
        expect(Object.keys(result).sort()).toEqual(newSegments.map((s) => s.key).sort())

        for (const seg of newSegments) {
          if (seg.key in oldData) {
            // (a) common segment → value preserved
            expect(result[seg.key]).toBe(oldData[seg.key])
          } else {
            // (b) newly added segment → zero-initialized
            expect(result[seg.key]).toBe(0)
          }
        }
      }),
    )
  })

  it('remapRowAgingData preserves common segments across all periods (3-period)', () => {
    // Feature: aging-config-enhancement, Property 10: Config change preserves existing segment data
    // **Validates: Requirements 4.5**
    const rowArb = fc.record({
      rowId: fc.string({ minLength: 1, maxLength: 8 }),
      agingPrior: agingDataArb,
      agingCurrent: agingDataArb,
      agingAudited: agingDataArb,
    })
    fc.assert(
      fc.property(rowArb, segmentsArb, (row, newSegments) => {
        const result = remapRowAgingData(row, newSegments, true)
        const keys = newSegments.map((s) => s.key).sort()
        for (const field of ['agingPrior', 'agingCurrent', 'agingAudited'] as const) {
          expect(Object.keys(result[field]).sort()).toEqual(keys)
          for (const seg of newSegments) {
            const expected = seg.key in row[field] ? row[field][seg.key] : 0
            expect(result[field][seg.key]).toBe(expected)
          }
        }
        // non-aging field preserved
        expect(result.rowId).toBe(row.rowId)
      }),
    )
  })

  it('remapRowAgingData omits agingCurrent for 2-period subjects', () => {
    // Feature: aging-config-enhancement, Property 10: Config change preserves existing segment data
    // **Validates: Requirements 4.5**
    const rowArb = fc.record({
      agingPrior: agingDataArb,
      agingAudited: agingDataArb,
    })
    fc.assert(
      fc.property(rowArb, segmentsArb, (row, newSegments) => {
        const result = remapRowAgingData(row, newSegments, false)
        expect(result.agingCurrent).toBeUndefined()
        const keys = newSegments.map((s) => s.key).sort()
        expect(Object.keys(result.agingPrior).sort()).toEqual(keys)
        expect(Object.keys(result.agingAudited).sort()).toEqual(keys)
      }),
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 11: Serialization produces exclusively nested format
// ══════════════════════════════════════════════════════════════════════════════

describe('useAgingMigration — Property 11: Serialization produces exclusively nested format', () => {
  it('migrated D2 row contains nested objects and NO flat aging keys', () => {
    // Feature: aging-config-enhancement, Property 11: Serialization produces exclusively nested format
    // **Validates: Requirements 4.2, 10.4**
    fc.assert(
      fc.property(legacyD2FlatRowArb, (raw) => {
        const migrated = migrateD2FlatToNested(raw)

        // Nested objects present
        expect(typeof migrated.agingPrior).toBe('object')
        expect(typeof migrated.agingCurrent).toBe('object')
        expect(typeof migrated.agingAudited).toBe('object')

        // NO flat keys survive
        for (const flatKey of D2_FLAT_KEYS) {
          expect(flatKey in migrated).toBe(false)
        }
      }),
    )
  })

  it('stripLegacyFlatKeys removes every flat key even from mixed rows', () => {
    // Feature: aging-config-enhancement, Property 11: Serialization produces exclusively nested format
    // **Validates: Requirements 4.2, 10.4**
    // Mixed row: some flat keys + already-nested objects + non-aging fields
    const mixedRowArb = fc.record({
      rowId: fc.string({ minLength: 1, maxLength: 8 }),
      agingPrior: fc.record(Object.fromEntries(FIVE_YEAR_KEYS.map((k) => [k, numArb]))),
      agingCurrent: fc.record(Object.fromEntries(FIVE_YEAR_KEYS.map((k) => [k, numArb]))),
      agingAudited: fc.record(Object.fromEntries(FIVE_YEAR_KEYS.map((k) => [k, numArb]))),
      ...Object.fromEntries(ALL_FLAT_KEYS.map((k) => [k, numArb])),
    })
    fc.assert(
      fc.property(mixedRowArb, (row) => {
        const cleaned = stripLegacyFlatKeys(row)
        for (const flatKey of D2_FLAT_KEYS) {
          expect(flatKey in cleaned).toBe(false)
        }
        // Nested objects + non-aging fields survive
        expect(cleaned.rowId).toBe(row.rowId)
        expect(cleaned.agingPrior).toEqual(row.agingPrior)
        expect(cleaned.agingCurrent).toEqual(row.agingCurrent)
        expect(cleaned.agingAudited).toEqual(row.agingAudited)
      }),
    )
  })

  it('serialized output round-trips through JSON without flat keys', () => {
    // Feature: aging-config-enhancement, Property 11: Serialization produces exclusively nested format
    // **Validates: Requirements 4.2, 10.4**
    fc.assert(
      fc.property(legacyD2FlatRowArb, (raw) => {
        const serialized = JSON.parse(JSON.stringify(migrateD2FlatToNested(raw)))
        for (const flatKey of D2_FLAT_KEYS) {
          expect(flatKey in serialized).toBe(false)
        }
        expect(serialized.agingPrior).toBeDefined()
        expect(serialized.agingCurrent).toBeDefined()
        expect(serialized.agingAudited).toBeDefined()
      }),
    )
  })
})
