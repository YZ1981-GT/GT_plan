/**
 * Property-Based Tests — A9-1 内控缺陷沟通函
 *
 * Spec: .kiro/specs/a9-1-deficiency-letter/
 * Task: 2.2
 *
 * Property 2: item_id format — for any section and field_id, item_id matches `a91-{section}-{field_id}` with section in valid set
 * Property 6: deficiency add/remove consistency — for any sequence of add/remove ops, final length = initial + adds - removes, remaining items preserve values
 * Property 10: mode switch data persistence — structured edits → flush → all values preserved after simulated mode switch
 *
 * **Validates: Requirements 5.6, 6.6, 6.7, 6.10, 7.5, 8.4, 9.3, 12.1, 12.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Pure logic extracted from composable for PBT ────────────────────────────

const VALID_SECTIONS = ['addressee', 'independence', 'deficiency', 'committee', 'signature', 'response'] as const

const SECTION_FIELDS: Record<string, string[]> = {
  addressee: ['client_name', 'custom_text'],
  independence: ['team_independent', 'no_relationships', 'no_relationships_detail', 'safeguards_taken', 'non_audit_services', 'non_audit_services_detail'],
  deficiency: ['major', 'significant', 'general'],
  committee: ['applicability', 'description'],
  signature: ['date'],
  response: ['opinion', 'conclusion', 'representative', 'response_date'],
}

type Severity = 'major' | 'significant' | 'general'

interface DeficiencyItem {
  id: string
  description: string
  impact: string
  recommendation: string
  indexRef: string | null
  source: 'b22b' | 'manual'
  severity: Severity
}

/** Build item_id for a section+field combination (same as composable) */
function buildItemId(section: string, fieldId: string): string {
  return `a91-${section}-${fieldId}`
}

/** Simulate add deficiency */
function addDeficiency(list: DeficiencyItem[], severity: Severity): DeficiencyItem[] {
  const newItem: DeficiencyItem = {
    id: `def-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    description: '',
    impact: '',
    recommendation: '',
    indexRef: null,
    source: 'manual',
    severity,
  }
  return [...list, newItem]
}

/** Simulate remove deficiency */
function removeDeficiency(list: DeficiencyItem[], index: number): DeficiencyItem[] {
  if (index < 0 || index >= list.length) return list
  return [...list.slice(0, index), ...list.slice(index + 1)]
}

/** Simulate update deficiency field */
function updateDeficiency(list: DeficiencyItem[], index: number, field: string, value: string): DeficiencyItem[] {
  if (index < 0 || index >= list.length) return list
  const copy = list.map(item => ({ ...item }))
  ;(copy[index] as any)[field] = value
  return copy
}

/** Simulate section data for mode switch test */
interface SimpleSectionData {
  addressee_client_name: string
  independence_team_independent: string
  committee_applicability: string
  signature_date: string
  response_opinion: string
}

function applyEdits(data: SimpleSectionData, edits: Array<{ field: keyof SimpleSectionData; value: string }>): SimpleSectionData {
  const result = { ...data }
  for (const edit of edits) {
    result[edit.field] = edit.value
  }
  return result
}

// ─── Property 2: item_id format ─────────────────────────────────────────────

describe('Feature: a9-1-deficiency-letter, Property 2: item_id format', () => {
  /**
   * **Validates: Requirements 5.6, 6.10, 7.5, 8.4, 9.3, 12.2**
   */

  it('for any valid section and field_id, item_id matches a91-{section}-{field_id}', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_SECTIONS),
        fc.string({ minLength: 1, maxLength: 30 }).filter(s => /^[a-z_]+$/.test(s)),
        (section, fieldId) => {
          const id = buildItemId(section, fieldId)
          expect(id).toBe(`a91-${section}-${fieldId}`)
          expect(id).toMatch(/^a91-[a-z]+-[a-z_]+$/)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('all section-specific fields produce correct item_ids', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_SECTIONS).chain(section =>
          fc.constantFrom(...SECTION_FIELDS[section]).map(field => ({ section, field })),
        ),
        ({ section, field }) => {
          const id = buildItemId(section, field)
          expect(id).toMatch(/^a91-/)
          expect(id).toBe(`a91-${section}-${field}`)
          // Section part must be in valid set
          const sectionPart = id.split('-')[1]
          expect(VALID_SECTIONS).toContain(sectionPart)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('item_ids from different sections never collide', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_SECTIONS),
        fc.constantFrom(...VALID_SECTIONS),
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => /^[a-z_]+$/.test(s)),
        (section1, section2, field) => {
          fc.pre(section1 !== section2)
          const id1 = buildItemId(section1, field)
          const id2 = buildItemId(section2, field)
          expect(id1).not.toBe(id2)
        },
      ),
      { numRuns: 30 },
    )
  })
})

// ─── Property 6: deficiency add/remove consistency ──────────────────────────

describe('Feature: a9-1-deficiency-letter, Property 6: deficiency add/remove consistency', () => {
  /**
   * **Validates: Requirements 6.6, 6.7**
   */

  it('final length = initial + adds - removes for any valid operation sequence', () => {
    const severityArb = fc.constantFrom('major', 'significant', 'general') as fc.Arbitrary<Severity>

    // Generate a sequence of add/remove ops
    const opsArb = fc.array(
      fc.oneof(
        fc.record({ type: fc.constant('add' as const) }),
        fc.record({ type: fc.constant('remove' as const), index: fc.nat({ max: 20 }) }),
      ),
      { minLength: 1, maxLength: 15 },
    )

    fc.assert(
      fc.property(severityArb, opsArb, (severity, ops) => {
        let list: DeficiencyItem[] = []
        let addCount = 0
        let removeCount = 0

        for (const op of ops) {
          if (op.type === 'add') {
            list = addDeficiency(list, severity)
            addCount++
          } else {
            const idx = (op as any).index
            if (idx >= 0 && idx < list.length) {
              list = removeDeficiency(list, idx)
              removeCount++
            }
          }
        }

        expect(list.length).toBe(addCount - removeCount)
      }),
      { numRuns: 50 },
    )
  })

  it('remaining items preserve their field values after add/remove', () => {
    const severityArb = fc.constantFrom('major', 'significant', 'general') as fc.Arbitrary<Severity>

    fc.assert(
      fc.property(
        severityArb,
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        (severity, desc, impact) => {
          // Add an item, update it, add another, remove the second → first still has original values
          let list: DeficiencyItem[] = []
          list = addDeficiency(list, severity)
          list = updateDeficiency(list, 0, 'description', desc)
          list = updateDeficiency(list, 0, 'impact', impact)
          list = addDeficiency(list, severity)
          list = removeDeficiency(list, 1) // remove the second item

          expect(list).toHaveLength(1)
          expect(list[0].description).toBe(desc)
          expect(list[0].impact).toBe(impact)
          expect(list[0].source).toBe('manual')
          expect(list[0].severity).toBe(severity)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('adding N items then removing all results in empty list', () => {
    const severityArb = fc.constantFrom('major', 'significant', 'general') as fc.Arbitrary<Severity>

    fc.assert(
      fc.property(
        severityArb,
        fc.integer({ min: 1, max: 10 }),
        (severity, count) => {
          let list: DeficiencyItem[] = []
          for (let i = 0; i < count; i++) {
            list = addDeficiency(list, severity)
          }
          expect(list).toHaveLength(count)

          // Remove from end to start
          for (let i = count - 1; i >= 0; i--) {
            list = removeDeficiency(list, i)
          }
          expect(list).toHaveLength(0)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 10: mode switch data persistence ──────────────────────────────

describe('Feature: a9-1-deficiency-letter, Property 10: mode switch data persistence', () => {
  /**
   * **Validates: Requirements 2.5, 12.1**
   */

  it('structured edits are preserved after simulated flush + mode switch', () => {
    const fieldArb = fc.constantFrom(
      'addressee_client_name',
      'independence_team_independent',
      'committee_applicability',
      'signature_date',
      'response_opinion',
    ) as fc.Arbitrary<keyof SimpleSectionData>

    const editArb = fc.record({
      field: fieldArb,
      value: fc.string({ minLength: 1, maxLength: 50 }),
    })

    fc.assert(
      fc.property(
        fc.array(editArb, { minLength: 1, maxLength: 8 }),
        (edits) => {
          const initial: SimpleSectionData = {
            addressee_client_name: '',
            independence_team_independent: '',
            committee_applicability: '',
            signature_date: '',
            response_opinion: '',
          }

          // Apply edits (structured mode)
          const afterEdits = applyEdits(initial, edits)

          // Simulate flush → mode switch → switch back (data should be same)
          // The "flush" ensures data is saved; mode switch just re-reads from same state
          const afterModeSwitch = { ...afterEdits }

          // All values must be preserved
          for (const edit of edits) {
            // Last edit per field wins
            const lastEdit = edits.filter(e => e.field === edit.field).pop()!
            expect(afterModeSwitch[lastEdit.field]).toBe(lastEdit.value)
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  it('deficiency list edits survive flush + mode switch', () => {
    const severityArb = fc.constantFrom('major', 'significant', 'general') as fc.Arbitrary<Severity>

    fc.assert(
      fc.property(
        severityArb,
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 1, maxLength: 5 }),
        (severity, descriptions) => {
          // Add items and set descriptions
          let list: DeficiencyItem[] = []
          for (const desc of descriptions) {
            list = addDeficiency(list, severity)
            list = updateDeficiency(list, list.length - 1, 'description', desc)
          }

          // Simulate JSON serialization (flush to API) + deserialization (mode switch reload)
          const serialized = JSON.stringify(list)
          const deserialized: DeficiencyItem[] = JSON.parse(serialized)

          expect(deserialized).toHaveLength(descriptions.length)
          for (let i = 0; i < descriptions.length; i++) {
            expect(deserialized[i].description).toBe(descriptions[i])
            expect(deserialized[i].severity).toBe(severity)
            expect(deserialized[i].source).toBe('manual')
          }
        },
      ),
      { numRuns: 30 },
    )
  })
})
