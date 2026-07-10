/**
 * Property-Based Tests for useAgingConfig composable
 *
 * Feature: aging-config-enhancement
 *
 * Covers:
 * - Property 5: Config-to-bands transformation with subject override
 * - Property 6: Three-period subject row generation (D2/K1/K3/G5)
 * - Property 7: Two-period subject row generation (D3/F1)
 *
 * Pure functions (segmentsToBands / createEmptyAgingData) are exercised directly.
 * The subject-override branch lives inside the composable, so it is exercised by
 * mounting useAgingConfig with a mocked API layer.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import * as fc from 'fast-check'
import { defineComponent, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

// ── Mock the API layer so the composable resolves a controlled response ──────
let mockConfigResponse: any = null
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(async () => mockConfigResponse),
  },
}))

import {
  segmentsToBands,
  createEmptyAgingData,
  useAgingConfig,
  PRESET_SEGMENTS,
  clearAgingConfigCache,
  type AgingSegment,
  type AgingPreset,
  type UseAgingConfigReturn,
} from '../useAgingConfig'

// ── Generators ───────────────────────────────────────────────────────────────

const THREE_PERIOD = ['D2', 'K1', 'K3', 'G5'] as const
const TWO_PERIOD = ['D3', 'F1'] as const

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

const subjectArb = fc.constantFrom(...THREE_PERIOD, ...TWO_PERIOD)
const presetArb = fc.constantFrom<AgingPreset>('THREE_YEAR', 'FIVE_YEAR')

// ── Composable mount harness ─────────────────────────────────────────────────

async function mountComposable(
  projectId: string,
  subject?: string,
): Promise<{ result: UseAgingConfigReturn; unmount: () => void }> {
  let captured: UseAgingConfigReturn | null = null
  const Comp = defineComponent({
    setup() {
      captured = useAgingConfig(ref(projectId), subject)
      return () => null
    },
  })
  const wrapper = mount(Comp)
  await flushPromises()
  return { result: captured!, unmount: () => wrapper.unmount() }
}

beforeEach(() => {
  clearAgingConfigCache()
  mockConfigResponse = null
})

// ── P5: Config-to-bands transformation with subject override ─────────────────

describe('useAgingConfig — Property 5: Config-to-bands transformation with subject override', () => {
  it('segmentsToBands produces N bands with correct key/label/field paths (three-period)', () => {
    // Feature: aging-config-enhancement, Property 5: Config-to-bands transformation with subject override
    // **Validates: Requirements 3.1, 3.2, 3.4**
    fc.assert(
      fc.property(segmentsArb(), fc.constantFrom(...THREE_PERIOD), (segments, subject) => {
        const bands = segmentsToBands(segments, subject)
        expect(bands.length).toBe(segments.length)
        segments.forEach((seg, i) => {
          expect(bands[i].key).toBe(seg.key)
          expect(bands[i].label).toBe(seg.label)
          expect(bands[i].priorField).toBe(`agingPrior.${seg.key}`)
          expect(bands[i].currentField).toBe(`agingCurrent.${seg.key}`)
          expect(bands[i].auditedField).toBe(`agingAudited.${seg.key}`)
        })
      }),
    )
  })

  it('segmentsToBands omits currentField for two-period subjects', () => {
    // Feature: aging-config-enhancement, Property 5: Config-to-bands transformation with subject override
    // **Validates: Requirements 3.1, 3.2, 3.4**
    fc.assert(
      fc.property(segmentsArb(), fc.constantFrom(...TWO_PERIOD), (segments, subject) => {
        const bands = segmentsToBands(segments, subject)
        expect(bands.length).toBe(segments.length)
        segments.forEach((seg, i) => {
          expect(bands[i].key).toBe(seg.key)
          expect(bands[i].label).toBe(seg.label)
          expect(bands[i].priorField).toBe(`agingPrior.${seg.key}`)
          expect(bands[i].currentField).toBe('')
          expect(bands[i].auditedField).toBe(`agingAudited.${seg.key}`)
        })
      }),
    )
  })

  it('composable exposes segments/bands matching effective_segments when no override', async () => {
    // Feature: aging-config-enhancement, Property 5: Config-to-bands transformation with subject override
    // **Validates: Requirements 3.1, 3.2, 3.4**
    await fc.assert(
      fc.asyncProperty(segmentsArb(), subjectArb, fc.uuid(), async (segments, subject, pid) => {
        clearAgingConfigCache()
        mockConfigResponse = {
          preset: 'CUSTOM',
          effective_segments: segments,
          subject_overrides: {},
        }
        const { result, unmount } = await mountComposable(pid, subject)
        try {
          expect(result.segments.value).toEqual(segments)
          expect(result.bands.value.length).toBe(segments.length)
          result.segments.value.forEach((seg, i) => {
            expect(result.bands.value[i].key).toBe(seg.key)
            expect(result.bands.value[i].label).toBe(seg.label)
          })
        } finally {
          unmount()
        }
      }),
      { numRuns: 25 },
    )
  })

  it('composable uses override preset segments when subject_override exists', async () => {
    // Feature: aging-config-enhancement, Property 5: Config-to-bands transformation with subject override
    // **Validates: Requirements 3.1, 3.2, 3.4**
    await fc.assert(
      fc.asyncProperty(
        segmentsArb(),
        subjectArb,
        presetArb,
        fc.uuid(),
        async (globalSegments, subject, overridePreset, pid) => {
          clearAgingConfigCache()
          mockConfigResponse = {
            preset: 'FIVE_YEAR',
            effective_segments: globalSegments,
            subject_overrides: { [subject]: overridePreset },
          }
          const { result, unmount } = await mountComposable(pid, subject)
          try {
            const expected = PRESET_SEGMENTS[overridePreset]
            expect(result.preset.value).toBe(overridePreset)
            expect(result.segments.value).toEqual(expected)
            expect(result.bands.value.length).toBe(expected.length)
          } finally {
            unmount()
          }
        },
      ),
      { numRuns: 25 },
    )
  })
})

// ── P6: Three-period subject row generation (D2/K1/K3/G5) ────────────────────

describe('useAgingConfig — Property 6: Three-period subject row generation (D2/K1/K3/G5)', () => {
  it('createEmptyAgingData yields agingPrior/agingCurrent/agingAudited each with N zeroed keys', () => {
    // Feature: aging-config-enhancement, Property 6: Three-period subject row generation (D2/K1/K3/G5)
    // **Validates: Requirements 4.1, 6.1, 6.2, 6.3**
    fc.assert(
      fc.property(segmentsArb(2, 10), fc.constantFrom(...THREE_PERIOD), (segments, subject) => {
        const data = createEmptyAgingData(segments, subject)
        const n = segments.length

        // agingCurrent must be present for three-period subjects
        expect(data.agingCurrent).toBeDefined()

        const groups = [data.agingPrior, data.agingCurrent!, data.agingAudited]
        for (const group of groups) {
          expect(Object.keys(group).length).toBe(n)
          for (const seg of segments) {
            expect(group[seg.key]).toBe(0)
          }
        }
      }),
    )
  })
})

// ── P7: Two-period subject row generation (D3/F1) ────────────────────────────

describe('useAgingConfig — Property 7: Two-period subject row generation (D3/F1)', () => {
  it('createEmptyAgingData yields agingPrior/agingAudited each with N zeroed keys and no agingCurrent', () => {
    // Feature: aging-config-enhancement, Property 7: Two-period subject row generation (D3/F1)
    // **Validates: Requirements 5.1, 5.2**
    fc.assert(
      fc.property(segmentsArb(2, 10), fc.constantFrom(...TWO_PERIOD), (segments, subject) => {
        const data = createEmptyAgingData(segments, subject)
        const n = segments.length

        // Two-period subjects must NOT have agingCurrent
        expect(data.agingCurrent).toBeUndefined()

        const groups = [data.agingPrior, data.agingAudited]
        for (const group of groups) {
          expect(Object.keys(group).length).toBe(n)
          for (const seg of segments) {
            expect(group[seg.key]).toBe(0)
          }
        }
      }),
    )
  })
})
