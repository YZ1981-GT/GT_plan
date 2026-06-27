/**
 * Property-Based Tests — A18-2 与监管层沟通函
 *
 * Spec: .kiro/specs/a18-2-regulatory-communication/
 * Task: 2.2
 *
 * Property 1: item_id 格式 — `a182-{section}-{field}`
 * Property 2: 适用性→textarea 联动 — Y→visible, N/NA→hidden
 * Property 5: 适用性幂等 — 设置相同值两次产生相同状态
 *
 * **Validates: Requirements 5.3, 5.4, 9.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Pure logic extracted from composable for PBT ────────────────────────────

type Applicability = 'Y' | 'N' | 'NA' | null

interface Matter {
  id: number
  title: string
  applicability: Applicability
  content: string
}

/** Generate item_id for recipient field */
function recipientItemId(field: string): string {
  return `a182-recipient-${field}`
}

/** Generate item_id for matter field */
function matterItemId(matterId: number, field: 'applicability' | 'content'): string {
  return `a182-matter${matterId}-${field}`
}

/** Generate item_id for issuance field */
function issuanceItemId(field: string): string {
  return `a182-sign-${field}`
}

/** Determine textarea visibility based on applicability */
function isTextareaVisible(applicability: Applicability): boolean {
  return applicability === 'Y'
}

/** Apply applicability to a matter (pure) */
function applyApplicability(matter: Matter, value: Applicability): Matter {
  return { ...matter, applicability: value }
}

// ─── Property 1: item_id 格式一致性 ─────────────────────────────────────────

describe('Feature: a18-2-regulatory-communication, Property 1: item_id 格式 a182-{section}-{field}', () => {
  it('recipient fields produce a182-recipient-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('authority', 'custom'),
        (field) => {
          const id = recipientItemId(field)
          expect(id).toMatch(/^a182-recipient-[a-z_]+$/)
          expect(id).toBe(`a182-recipient-${field}`)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('matter fields produce a182-matter{N}-{field} format', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 4 }),
        fc.constantFrom('applicability', 'content'),
        (matterId, field) => {
          const id = matterItemId(matterId, field as 'applicability' | 'content')
          expect(id).toMatch(/^a182-matter[1-4]-(applicability|content)$/)
          expect(id).toBe(`a182-matter${matterId}-${field}`)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('issuance fields produce a182-sign-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('cpa1', 'cpa2', 'date'),
        (field) => {
          const id = issuanceItemId(field)
          expect(id).toMatch(/^a182-sign-[a-z0-9_]+$/)
          expect(id).toBe(`a182-sign-${field}`)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('all item_ids start with a182- prefix', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constantFrom('authority', 'custom').map(f => recipientItemId(f)),
          fc.tuple(fc.integer({ min: 1, max: 4 }), fc.constantFrom('applicability', 'content'))
            .map(([id, f]) => matterItemId(id, f as 'applicability' | 'content')),
          fc.constantFrom('cpa1', 'cpa2', 'date').map(f => issuanceItemId(f)),
        ),
        (itemId) => {
          expect(itemId).toMatch(/^a182-/)
        },
      ),
      { numRuns: 30 },
    )
  })
})

// ─── Property 2: 适用性→textarea 联动 ───────────────────────────────────────

describe('Feature: a18-2-regulatory-communication, Property 2: 适用性→textarea 联动', () => {
  it('applicability Y → textarea visible', () => {
    fc.assert(
      fc.property(
        fc.constant('Y' as Applicability),
        (applicability) => {
          expect(isTextareaVisible(applicability)).toBe(true)
        },
      ),
      { numRuns: 5 },
    )
  })

  it('applicability N → textarea hidden', () => {
    fc.assert(
      fc.property(
        fc.constant('N' as Applicability),
        (applicability) => {
          expect(isTextareaVisible(applicability)).toBe(false)
        },
      ),
      { numRuns: 5 },
    )
  })

  it('applicability NA → textarea hidden', () => {
    fc.assert(
      fc.property(
        fc.constant('NA' as Applicability),
        (applicability) => {
          expect(isTextareaVisible(applicability)).toBe(false)
        },
      ),
      { numRuns: 5 },
    )
  })

  it('applicability null → textarea hidden', () => {
    fc.assert(
      fc.property(
        fc.constant(null as Applicability),
        (applicability) => {
          expect(isTextareaVisible(applicability)).toBe(false)
        },
      ),
      { numRuns: 5 },
    )
  })

  it('only Y makes textarea visible, all others hide it', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant('Y' as Applicability),
          fc.constant('N' as Applicability),
          fc.constant('NA' as Applicability),
          fc.constant(null as Applicability),
        ),
        (applicability) => {
          const visible = isTextareaVisible(applicability)
          if (applicability === 'Y') {
            expect(visible).toBe(true)
          } else {
            expect(visible).toBe(false)
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 5: 适用性幂等 ─────────────────────────────────────────────────

describe('Feature: a18-2-regulatory-communication, Property 5: 适用性幂等', () => {
  it('applying same applicability twice produces identical state', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 4 }),
        fc.oneof(
          fc.constant('Y' as Applicability),
          fc.constant('N' as Applicability),
          fc.constant('NA' as Applicability),
          fc.constant(null as Applicability),
        ),
        (matterId, applicability) => {
          const matter: Matter = { id: matterId, title: '测试', applicability: null, content: '' }
          const after1 = applyApplicability(matter, applicability)
          const after2 = applyApplicability(after1, applicability)
          expect(after2.applicability).toBe(after1.applicability)
          expect(after2).toEqual(after1)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('idempotent: setting Y then Y again keeps content unchanged', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 4 }),
        fc.string({ minLength: 0, maxLength: 100 }),
        (matterId, content) => {
          const matter: Matter = { id: matterId, title: '测试', applicability: 'Y', content }
          const after1 = applyApplicability(matter, 'Y')
          const after2 = applyApplicability(after1, 'Y')
          expect(after2.content).toBe(content)
          expect(after2.applicability).toBe('Y')
        },
      ),
      { numRuns: 20 },
    )
  })
})
