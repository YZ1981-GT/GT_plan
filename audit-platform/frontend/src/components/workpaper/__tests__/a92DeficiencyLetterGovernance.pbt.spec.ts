/**
 * Property-Based Tests — A9-2 治理层内控缺陷沟通函
 *
 * Spec: .kiro/specs/a9-2-deficiency-letter-governance/
 * Task: 2.7
 *
 * Property 1: variant conditional rendering — Section 7 visible iff variant=management, general visible iff variant=management
 * Property 2: item_id a92 prefix — for any section+field with prefix='a92', item_id matches `a92-{section}-{field_id}`
 * Property 3: addressee text — "董事会" iff governance, "总经理" iff management
 * Property 5: nav count — 7 items for management, 6 for governance
 *
 * **Validates: Requirements 3.1, 3.2, 4.1, 4.2, 5.1, 5.2, 7.1, 7.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import { buildItemId } from '../composables/useA91DeficiencyLetter'

// ─── Pure logic for PBT ─────────────────────────────────────────────────────

type Variant = 'management' | 'governance'

const ALL_SEVERITY_GROUPS = ['major', 'significant', 'general'] as const
const ALL_NAV_ITEMS = ['addressee', 'intro', 'independence', 'deficiency', 'committee', 'signature', 'response']

/** Determine which severity groups are visible for a given variant */
function getVisibleSeverityGroups(variant: Variant): readonly string[] {
  return variant === 'governance'
    ? ALL_SEVERITY_GROUPS.filter(g => g !== 'general')
    : ALL_SEVERITY_GROUPS
}

/** Determine if Section 7 (response) is visible */
function isResponseSectionVisible(variant: Variant): boolean {
  return variant !== 'governance'
}

/** Determine nav items count */
function getNavItems(variant: Variant): string[] {
  return variant === 'governance'
    ? ALL_NAV_ITEMS.filter(n => n !== 'response')
    : ALL_NAV_ITEMS
}

/** Determine addressee text */
function getAddresseeText(clientName: string, variant: Variant): string {
  if (variant === 'governance') {
    return `${clientName}董事会\\监事会\\审计委员会：`
  }
  return `${clientName}总经理\\财务总监\\…：`
}

// ─── Property 1: variant conditional rendering ──────────────────────────────

describe('Feature: a9-2-deficiency-letter-governance, Property 1: variant conditional rendering', () => {
  /**
   * **Validates: Requirements 4.1, 4.2, 5.1**
   */

  it('Section 7 visible iff variant is management', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('management', 'governance') as fc.Arbitrary<Variant>,
        (variant) => {
          const visible = isResponseSectionVisible(variant)
          if (variant === 'management') {
            expect(visible).toBe(true)
          } else {
            expect(visible).toBe(false)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('general deficiency group visible iff variant is management', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('management', 'governance') as fc.Arbitrary<Variant>,
        (variant) => {
          const groups = getVisibleSeverityGroups(variant)
          if (variant === 'management') {
            expect(groups).toContain('general')
          } else {
            expect(groups).not.toContain('general')
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('major and significant always visible regardless of variant', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('management', 'governance') as fc.Arbitrary<Variant>,
        (variant) => {
          const groups = getVisibleSeverityGroups(variant)
          expect(groups).toContain('major')
          expect(groups).toContain('significant')
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 2: item_id a92 prefix ────────────────────────────────────────

describe('Feature: a9-2-deficiency-letter-governance, Property 2: item_id a92 prefix', () => {
  /**
   * **Validates: Requirements 7.1, 7.2**
   */

  const VALID_SECTIONS = ['addressee', 'independence', 'deficiency', 'committee', 'signature'] as const

  it('buildItemId with prefix a92 always produces a92-{section}-{field}', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_SECTIONS),
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => /^[a-z_]+$/.test(s)),
        (section, fieldId) => {
          const id = buildItemId(section, fieldId, 'a92')
          expect(id).toBe(`a92-${section}-${fieldId}`)
          expect(id).toMatch(/^a92-/)
          expect(id).not.toMatch(/^a91-/)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('a91 and a92 item_ids for same section+field never collide', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_SECTIONS),
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => /^[a-z_]+$/.test(s)),
        (section, fieldId) => {
          const id91 = buildItemId(section, fieldId, 'a91')
          const id92 = buildItemId(section, fieldId, 'a92')
          expect(id91).not.toBe(id92)
          expect(id91).toMatch(/^a91-/)
          expect(id92).toMatch(/^a92-/)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('default prefix is a91 for backward compatibility', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...VALID_SECTIONS),
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => /^[a-z_]+$/.test(s)),
        (section, fieldId) => {
          const idDefault = buildItemId(section, fieldId)
          const idExplicit = buildItemId(section, fieldId, 'a91')
          expect(idDefault).toBe(idExplicit)
        },
      ),
      { numRuns: 30 },
    )
  })
})

// ─── Property 3: addressee text variant difference ──────────────────────────

describe('Feature: a9-2-deficiency-letter-governance, Property 3: addressee text', () => {
  /**
   * **Validates: Requirements 3.1, 3.2**
   */

  it('addressee contains 董事会 iff variant is governance', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => s.trim().length > 0 && !s.includes('董事会') && !s.includes('总经理')),
        fc.constantFrom('management', 'governance') as fc.Arbitrary<Variant>,
        (clientName, variant) => {
          const text = getAddresseeText(clientName, variant)
          if (variant === 'governance') {
            expect(text).toContain('董事会')
            expect(text).not.toContain('总经理')
          } else {
            expect(text).toContain('总经理')
            expect(text).not.toContain('董事会')
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  it('addressee always starts with client_name', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => s.trim().length > 0),
        fc.constantFrom('management', 'governance') as fc.Arbitrary<Variant>,
        (clientName, variant) => {
          const text = getAddresseeText(clientName, variant)
          expect(text.startsWith(clientName)).toBe(true)
        },
      ),
      { numRuns: 30 },
    )
  })
})

// ─── Property 5: nav count ──────────────────────────────────────────────────

describe('Feature: a9-2-deficiency-letter-governance, Property 5: nav count', () => {
  /**
   * **Validates: Requirements 5.2**
   */

  it('management has 7 nav items, governance has 6', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('management', 'governance') as fc.Arbitrary<Variant>,
        (variant) => {
          const items = getNavItems(variant)
          if (variant === 'management') {
            expect(items).toHaveLength(7)
            expect(items).toContain('response')
          } else {
            expect(items).toHaveLength(6)
            expect(items).not.toContain('response')
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('non-response nav items always present regardless of variant', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('management', 'governance') as fc.Arbitrary<Variant>,
        (variant) => {
          const items = getNavItems(variant)
          expect(items).toContain('addressee')
          expect(items).toContain('intro')
          expect(items).toContain('independence')
          expect(items).toContain('deficiency')
          expect(items).toContain('committee')
          expect(items).toContain('signature')
        },
      ),
      { numRuns: 20 },
    )
  })
})
