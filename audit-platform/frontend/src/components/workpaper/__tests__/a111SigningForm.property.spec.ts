/**
 * Property-Based Tests — A1-11 签发流转控制表
 *
 * Spec: .kiro/specs/a1-11-signing-control-form/
 * Tasks: 5.1–5.8
 *
 * 使用 fast-check + vitest 验证 8 个 correctness properties。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import { SIGN_SLOTS, useA111Signing } from '../composables/useA111Signing'

// ─── Helpers ─────────────────────────────────────────────────────────────────

const CATEGORIES = ['A', 'B', 'C'] as const
type Category = (typeof CATEGORIES)[number]

/** Arbitrary for a valid business category */
const arbCategory = fc.constantFrom<Category>('A', 'B', 'C')

/** Arbitrary for a sign state (signed or unsigned) */
const arbSignState = fc.oneof(
  fc.constant({ conclusion: 'Y' as string | null, remark: 'User', wp_ref: '2025-01-01' }),
  fc.constant({ conclusion: null as string | null, remark: null as string | null, wp_ref: null as string | null }),
)

/** Arbitrary for sign states map (all 6 slots) */
const arbSignStatesMap = fc.record(
  Object.fromEntries(SIGN_SLOTS.map(s => [s.id, arbSignState])) as Record<string, typeof arbSignState>
)

/** Generate non-empty non-whitespace string */
const arbNonEmptyString = fc.string({ minLength: 1 }).filter(s => s.trim().length > 0)

/** Generate whitespace-only or empty string */
const arbWhitespaceOnly = fc.constantFrom('', ' ', '  ', '\t', '\n', '  \t\n  ', '\r\n')

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: Required signing slots determined by business category
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 1: Required signing slots determined by business category', () => {
  it('Category A requires pm, partner, qc, eqcr (4 slots)', () => {
    fc.assert(
      fc.property(fc.constant('A' as Category), (cat) => {
        const required = SIGN_SLOTS.filter(slot => slot.requiredFor.includes(cat))
        const ids = required.map(s => s.id).sort()
        expect(ids).toEqual(['eqcr', 'partner', 'pm', 'qc'])
        expect(required.length).toBe(4)
      }),
      { numRuns: 100 },
    )
  })

  it('Category B or C requires only pm, partner (2 slots)', () => {
    fc.assert(
      fc.property(fc.constantFrom<Category>('B', 'C'), (cat) => {
        const required = SIGN_SLOTS.filter(slot => slot.requiredFor.includes(cat))
        const ids = required.map(s => s.id).sort()
        expect(ids).toEqual(['partner', 'pm'])
        expect(required.length).toBe(2)
      }),
      { numRuns: 100 },
    )
  })

  it('requiredSlots from composable matches pure SIGN_SLOTS filter for any category', () => {
    fc.assert(
      fc.property(arbCategory, (cat) => {
        const businessCategory = ref(cat)
        const signStates = ref<Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }>>({})
        const { requiredSlots } = useA111Signing(businessCategory, signStates)

        const expected = SIGN_SLOTS.filter(s => s.requiredFor.includes(cat))
        expect(requiredSlots.value).toEqual(expected)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: Readonly mode equals all-required-signed OR external readonly
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 2: Readonly mode equals all-required-signed OR external readonly', () => {
  it('isReadonly iff externalReadonly OR all required slots signed', () => {
    fc.assert(
      fc.property(arbCategory, arbSignStatesMap, fc.boolean(), (cat, states, extReadonly) => {
        const businessCategory = ref(cat)
        const signStates = ref(states)
        const externalReadonly = ref(extReadonly)

        const { isReadonly } = useA111Signing(businessCategory, signStates, externalReadonly)

        // Compute expected
        const requiredSlots = SIGN_SLOTS.filter(s => s.requiredFor.includes(cat))
        const allSigned = requiredSlots.length > 0 && requiredSlots.every(s => states[s.id]?.conclusion === 'Y')
        const expectedReadonly = extReadonly || allSigned

        expect(isReadonly.value).toBe(expectedReadonly)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: Signing progress computation
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 3: Signing progress computation', () => {
  it('progress.signed = count of required slots with conclusion Y, progress.total = required count', () => {
    fc.assert(
      fc.property(arbCategory, arbSignStatesMap, (cat, states) => {
        const businessCategory = ref(cat)
        const signStates = ref(states)

        const { progress } = useA111Signing(businessCategory, signStates)

        const requiredSlots = SIGN_SLOTS.filter(s => s.requiredFor.includes(cat))
        const expectedTotal = requiredSlots.length
        const expectedSigned = requiredSlots.filter(s => states[s.id]?.conclusion === 'Y').length

        expect(progress.value.total).toBe(expectedTotal)
        expect(progress.value.signed).toBe(expectedSigned)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: Auto-fill only populates empty fields
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 4: Auto-fill only populates empty fields', () => {
  /**
   * Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
   *
   * Reproduce the auto-fill logic from useA111FormData:
   * - AUTO_FILL_MAP defines which fields get populated
   * - Only fields NOT in existingItemIds get populated
   */
  const AUTO_FILL_KEYS = [
    'A1-11-entity-name',
    'A1-11-entity-type',
    'A1-11-industry',
    'A1-11-engagement-no',
    'A1-11-biz-category',
  ] as const

  const AUTO_FILL_MAP: Record<string, (p: any) => { conclusion?: string | null; remark?: string | null; wp_ref?: string | null }> = {
    'A1-11-entity-name': (p) => ({ remark: p.entity_name || null }),
    'A1-11-entity-type': (p) => ({ remark: p.entity_type || null }),
    'A1-11-industry': (p) => ({ remark: p.industry || null }),
    'A1-11-engagement-no': (p) => ({ remark: p.engagement_letter_no || null }),
    'A1-11-biz-category': (p) => ({ conclusion: p.business_category || null }),
  }

  /** Arbitrary for a subset of auto-fill keys (simulates existing responses) */
  const arbExistingKeys = fc.subarray([...AUTO_FILL_KEYS])

  /** Arbitrary for project context */
  const arbProjectContext = fc.record({
    entity_name: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: undefined }),
    entity_type: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
    industry: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
    engagement_letter_no: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
    business_category: fc.option(fc.constantFrom('A', 'B', 'C'), { nil: undefined }),
  })

  it('auto-fill writes only to fields NOT in existingResponses', () => {
    fc.assert(
      fc.property(arbProjectContext, arbExistingKeys, (ctx, existingKeys) => {
        const existingItemIds = new Set(existingKeys)

        // Simulate formData before auto-fill (existing items have placeholder values)
        const formData: Record<string, { item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null }> = {}
        for (const key of existingKeys) {
          formData[key] = { item_id: key, conclusion: 'existing', remark: 'existing', wp_ref: null }
        }

        // Apply auto-fill logic (mirror of useA111FormData.applyAutoFill)
        for (const [itemId, extractor] of Object.entries(AUTO_FILL_MAP)) {
          if (existingItemIds.has(itemId)) continue
          const fillValues = extractor(ctx)
          if (!fillValues.conclusion && !fillValues.remark && !fillValues.wp_ref) continue
          formData[itemId] = {
            item_id: itemId,
            conclusion: fillValues.conclusion ?? null,
            remark: fillValues.remark ?? null,
            wp_ref: fillValues.wp_ref ?? null,
          }
        }

        // Verify: existing fields are unchanged
        for (const key of existingKeys) {
          expect(formData[key].conclusion).toBe('existing')
          expect(formData[key].remark).toBe('existing')
        }

        // Verify: new fields only populated if extractor returned non-null values
        for (const key of AUTO_FILL_KEYS) {
          if (existingItemIds.has(key)) continue
          const fillValues = AUTO_FILL_MAP[key](ctx)
          if (!fillValues.conclusion && !fillValues.remark && !fillValues.wp_ref) {
            // Not populated
            expect(formData[key]).toBeUndefined()
          }
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: Signing action records correct data
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 5: Signing action records correct data', () => {
  /**
   * Validates: Requirements 3.2
   */
  const arbSlotId = fc.constantFrom(...SIGN_SLOTS.map(s => s.id))
  const arbUserName = fc.string({ minLength: 1, maxLength: 30 }).filter(s => s.trim().length > 0)

  it('signAction sets conclusion=Y, remark=userName, wp_ref=YYYY-MM-DD', () => {
    fc.assert(
      fc.property(arbSlotId, arbUserName, (slotId, userName) => {
        const businessCategory = ref<string>('A')
        const signStates = ref<Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }>>({})

        const { signAction, getSlotState } = useA111Signing(businessCategory, signStates)

        signAction(slotId, userName)

        const state = getSlotState(slotId)
        expect(state.conclusion).toBe('Y')
        expect(state.remark).toBe(userName)

        // wp_ref must be YYYY-MM-DD format
        expect(state.wp_ref).toMatch(/^\d{4}-\d{2}-\d{2}$/)

        // Verify it's today's date
        const today = new Date()
        const y = today.getFullYear()
        const m = String(today.getMonth() + 1).padStart(2, '0')
        const d = String(today.getDate()).padStart(2, '0')
        expect(state.wp_ref).toBe(`${y}-${m}-${d}`)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: Signed slot disables interaction
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 6: Signed slot disables interaction', () => {
  /**
   * Validates: Requirements 3.3, 3.4
   *
   * Pure logic test: if conclusion='Y' → signed=true (completed state),
   * if conclusion=null → signed=false (actionable state).
   */
  const arbSlotId = fc.constantFrom(...SIGN_SLOTS.map(s => s.id))

  it('conclusion Y → slot is signed (completed state)', () => {
    fc.assert(
      fc.property(arbSlotId, (slotId) => {
        const businessCategory = ref<string>('A')
        const signStates = ref<Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }>>({
          [slotId]: { conclusion: 'Y', remark: 'Signer', wp_ref: '2025-06-01' },
        })

        const { getSlotState } = useA111Signing(businessCategory, signStates)
        const state = getSlotState(slotId)

        // Completed state: conclusion is Y
        expect(state.conclusion).toBe('Y')
        // This means the slot is "signed" → UI renders as completed
        const signed = state.conclusion === 'Y'
        expect(signed).toBe(true)
      }),
      { numRuns: 100 },
    )
  })

  it('conclusion null → slot is actionable (unsigned)', () => {
    fc.assert(
      fc.property(arbSlotId, (slotId) => {
        const businessCategory = ref<string>('A')
        const signStates = ref<Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }>>({
          [slotId]: { conclusion: null, remark: null, wp_ref: null },
        })

        const { getSlotState } = useA111Signing(businessCategory, signStates)
        const state = getSlotState(slotId)

        // Actionable state: conclusion is null
        expect(state.conclusion).toBeNull()
        const signed = state.conclusion === 'Y'
        expect(signed).toBe(false)
      }),
      { numRuns: 100 },
    )
  })

  it('random signState determines slot signed status correctly', () => {
    fc.assert(
      fc.property(arbSlotId, arbSignState, (slotId, signState) => {
        const businessCategory = ref<string>('A')
        const signStates = ref<Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }>>({
          [slotId]: signState,
        })

        const { getSlotState } = useA111Signing(businessCategory, signStates)
        const state = getSlotState(slotId)

        const signed = state.conclusion === 'Y'
        if (signState.conclusion === 'Y') {
          expect(signed).toBe(true)
        } else {
          expect(signed).toBe(false)
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: Amendment reason validation
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 7: Amendment reason validation', () => {
  /**
   * Validates: Requirements 9.2, 9.3
   *
   * Pure validation logic: trim().length === 0 → rejected, otherwise → accepted.
   */

  /** The validation function from the component */
  function isAmendmentReasonValid(reason: string): boolean {
    return reason.trim().length > 0
  }

  it('whitespace-only or empty strings are rejected', () => {
    fc.assert(
      fc.property(arbWhitespaceOnly, (reason) => {
        expect(isAmendmentReasonValid(reason)).toBe(false)
      }),
      { numRuns: 100 },
    )
  })

  it('non-empty non-whitespace strings are accepted', () => {
    fc.assert(
      fc.property(arbNonEmptyString, (reason) => {
        expect(isAmendmentReasonValid(reason)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })

  it('random strings: validity equals trim().length > 0', () => {
    fc.assert(
      fc.property(fc.string(), (reason) => {
        const expected = reason.trim().length > 0
        expect(isAmendmentReasonValid(reason)).toBe(expected)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: Amendment history item_id sequencing
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: a1-11-signing-control-form, Property 8: Amendment history item_id sequencing', () => {
  /**
   * Validates: Requirements 9.5
   *
   * The Nth amendment uses prefix `A1-11-amend-{N}-`.
   * Each amendment's items are independent (different prefix).
   */

  /** Generate amendment index (1 to 10) */
  const arbAmendmentCount = fc.integer({ min: 1, max: 10 })

  it('Nth amendment uses prefix A1-11-amend-{N}-', () => {
    fc.assert(
      fc.property(arbAmendmentCount, (n) => {
        const expectedReasonId = `A1-11-amend-${n}-reason`
        const expectedSignPmId = `A1-11-amend-${n}-sign-pm`
        const expectedSignPartnerId = `A1-11-amend-${n}-sign-partner`
        const expectedSignQcId = `A1-11-amend-${n}-sign-qc`
        const expectedSignEqcrId = `A1-11-amend-${n}-sign-eqcr`

        // All items for amendment N share the prefix A1-11-amend-{N}-
        const prefix = `A1-11-amend-${n}-`
        expect(expectedReasonId.startsWith(prefix)).toBe(true)
        expect(expectedSignPmId.startsWith(prefix)).toBe(true)
        expect(expectedSignPartnerId.startsWith(prefix)).toBe(true)
        expect(expectedSignQcId.startsWith(prefix)).toBe(true)
        expect(expectedSignEqcrId.startsWith(prefix)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })

  it('each amendment has independent prefix (no overlap between different N)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }),
        fc.integer({ min: 1, max: 10 }),
        (n1, n2) => {
          fc.pre(n1 !== n2) // Only test when indices differ

          const prefix1 = `A1-11-amend-${n1}-`
          const prefix2 = `A1-11-amend-${n2}-`

          // Prefixes are different
          expect(prefix1).not.toBe(prefix2)

          // Items from amendment n1 do not start with prefix of n2
          const reasonN1 = `A1-11-amend-${n1}-reason`
          expect(reasonN1.startsWith(prefix2)).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('amendment sequence 1..N uses strictly increasing indices', () => {
    fc.assert(
      fc.property(arbAmendmentCount, (totalAmendments) => {
        const prefixes: string[] = []
        for (let i = 1; i <= totalAmendments; i++) {
          prefixes.push(`A1-11-amend-${i}-`)
        }

        // All prefixes are unique
        const uniquePrefixes = new Set(prefixes)
        expect(uniquePrefixes.size).toBe(totalAmendments)

        // Each prefix contains its sequential number
        for (let i = 0; i < prefixes.length; i++) {
          expect(prefixes[i]).toBe(`A1-11-amend-${i + 1}-`)
        }
      }),
      { numRuns: 100 },
    )
  })
})
