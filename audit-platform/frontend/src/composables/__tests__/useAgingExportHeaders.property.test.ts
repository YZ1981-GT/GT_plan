/**
 * Property-Based Tests for buildAgingExportHeaders (useAgingConfig)
 *
 * Feature: aging-config-enhancement
 *
 * Covers:
 * - Property 12: Export header generation from bands
 *
 * buildAgingExportHeaders is a pure function that turns a bands array into the
 * dynamic aging column headers used by the export service. It is exercised
 * directly with fast-check-generated bands.
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  segmentsToBands,
  buildAgingExportHeaders,
  AGING_EXPORT_PERIOD_LABELS,
  type AgingSegment,
} from '../useAgingConfig'

const THREE_PERIOD = ['D2', 'K1', 'K3', 'G5', 'F1'] as const
const TWO_PERIOD = ['D3'] as const

/** Generate N segments (2..10) with unique keys and derived labels. */
function segmentsArb(min = 2, max = 10): fc.Arbitrary<AgingSegment[]> {
  return fc
    .uniqueArray(
      fc.string({ minLength: 1, maxLength: 8 }).filter((s) => s.trim().length > 0),
      { minLength: min, maxLength: max },
    )
    .map((keys) =>
      keys.map((key, i) => ({
        key,
        label: `段${i}_${key}`,
        dayFrom: i * 365,
        dayTo: i === keys.length - 1 ? null : (i + 1) * 365,
      })),
    )
}

describe('buildAgingExportHeaders — Property 12: Export header generation from bands', () => {
  it('three-period subjects (D2/K1/K3/G5) produce 3N headers with all labels + 3 prefixes', () => {
    // Feature: aging-config-enhancement, Property 12: Export header generation from bands
    // **Validates: Requirements 8.1**
    fc.assert(
      fc.property(segmentsArb(), fc.constantFrom(...THREE_PERIOD), (segments, subject) => {
        const bands = segmentsToBands(segments, subject)
        const headers = buildAgingExportHeaders(bands, subject)
        const n = segments.length

        // 3N headers for three-period subjects
        expect(headers.length).toBe(3 * n)

        // every label appears with each period prefix
        for (const seg of segments) {
          expect(headers).toContain(`${seg.label}(${AGING_EXPORT_PERIOD_LABELS.prior})`)
          expect(headers).toContain(`${seg.label}(${AGING_EXPORT_PERIOD_LABELS.current})`)
          expect(headers).toContain(`${seg.label}(${AGING_EXPORT_PERIOD_LABELS.audited})`)
        }

        // headers unique (unique labels/keys → unique headers)
        expect(new Set(headers).size).toBe(headers.length)
      }),
    )
  })

  it('two-period subjects (D3) produce 2N headers with only prior + audited prefixes', () => {
    // Feature: aging-config-enhancement, Property 12: Export header generation from bands
    // **Validates: Requirements 8.1**
    fc.assert(
      fc.property(segmentsArb(), fc.constantFrom(...TWO_PERIOD), (segments, subject) => {
        const bands = segmentsToBands(segments, subject)
        const headers = buildAgingExportHeaders(bands, subject)
        const n = segments.length

        // 2N headers for two-period subjects
        expect(headers.length).toBe(2 * n)

        for (const seg of segments) {
          expect(headers).toContain(`${seg.label}(${AGING_EXPORT_PERIOD_LABELS.prior})`)
          expect(headers).toContain(`${seg.label}(${AGING_EXPORT_PERIOD_LABELS.audited})`)
          // no 期末未审 column for two-period subjects
          expect(headers).not.toContain(`${seg.label}(${AGING_EXPORT_PERIOD_LABELS.current})`)
        }

        expect(new Set(headers).size).toBe(headers.length)
      }),
    )
  })

  it('header order follows bands order, grouped per band (prior[,current],audited)', () => {
    // Feature: aging-config-enhancement, Property 12: Export header generation from bands
    // **Validates: Requirements 8.1**
    fc.assert(
      fc.property(segmentsArb(), fc.constantFrom(...THREE_PERIOD, ...TWO_PERIOD), (segments, subject) => {
        const bands = segmentsToBands(segments, subject)
        const headers = buildAgingExportHeaders(bands, subject)
        const isThreePeriod = (THREE_PERIOD as readonly string[]).includes(subject)
        const perBand = isThreePeriod ? 3 : 2

        bands.forEach((band, i) => {
          const slice = headers.slice(i * perBand, (i + 1) * perBand)
          const expected = isThreePeriod
            ? [
                `${band.label}(${AGING_EXPORT_PERIOD_LABELS.prior})`,
                `${band.label}(${AGING_EXPORT_PERIOD_LABELS.current})`,
                `${band.label}(${AGING_EXPORT_PERIOD_LABELS.audited})`,
              ]
            : [
                `${band.label}(${AGING_EXPORT_PERIOD_LABELS.prior})`,
                `${band.label}(${AGING_EXPORT_PERIOD_LABELS.audited})`,
              ]
          expect(slice).toEqual(expected)
        })
      }),
    )
  })
})
