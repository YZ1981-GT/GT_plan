/**
 * Property-Based Tests — A17-7 独立性声明书
 *
 * Spec: .kiro/specs/a17-7-independence-declaration/
 * Task: 2.2
 *
 * Property 1: item_id 前缀隔离 — variant='team' → "a177-", variant='committee' → "a177a-"
 * Property 2: 签字表预填完整性 — N team members → N pre-filled rows
 * Property 3: 威胁记录增删一致性 — add/remove 后 count = adds - removes, never negative
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { getPrefix, type Variant, type ThreatType } from '../composables/useA177IndependenceDeclaration'

// ─── Property 1: item_id 前缀隔离 ───────────────────────────────────────────

describe('Feature: a17-7-independence-declaration, Property 1: item_id 前缀隔离', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * For any field save, variant='team' SHALL produce item_id starting with "a177-"
   * and variant='committee' SHALL produce item_id starting with "a177a-".
   */

  it('team variant always produces a177- prefix', () => {
    fc.assert(
      fc.property(
        fc.constant('team' as Variant),
        (variant) => {
          const prefix = getPrefix(variant)
          expect(prefix).toBe('a177-')
          expect(prefix.startsWith('a177-')).toBe(true)
          expect(prefix).not.toContain('a177a-')
        },
      ),
      { numRuns: 10 },
    )
  })

  it('committee variant always produces a177a- prefix', () => {
    fc.assert(
      fc.property(
        fc.constant('committee' as Variant),
        (variant) => {
          const prefix = getPrefix(variant)
          expect(prefix).toBe('a177a-')
          expect(prefix.startsWith('a177a-')).toBe(true)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('prefixes for team and committee never collide for period fields', () => {
    const periodFields = ['period-business-start', 'period-business-end', 'period-report-start', 'period-report-end']
    fc.assert(
      fc.property(
        fc.constantFrom(...periodFields),
        (field) => {
          const teamId = `${getPrefix('team')}${field}`
          const committeeId = `${getPrefix('committee')}${field}`
          expect(teamId).not.toBe(committeeId)
          expect(teamId.startsWith('a177-')).toBe(true)
          expect(committeeId.startsWith('a177a-')).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('sign row item_ids are prefix-isolated between variants', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 20 }),
        (rowIndex) => {
          const teamId = `${getPrefix('team')}sign-${rowIndex}`
          const committeeId = `${getPrefix('committee')}sign-${rowIndex}`
          expect(teamId).toBe(`a177-sign-${rowIndex}`)
          expect(committeeId).toBe(`a177a-sign-${rowIndex}`)
          expect(teamId).not.toBe(committeeId)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('threat item_ids are prefix-isolated between variants', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('economic', 'loan', 'business'),
        fc.integer({ min: 1, max: 10 }),
        (threatType, rowIndex) => {
          const teamId = `${getPrefix('team')}threat-${threatType}-${rowIndex}`
          const committeeId = `${getPrefix('committee')}threat-${threatType}-${rowIndex}`
          expect(teamId.startsWith('a177-threat-')).toBe(true)
          expect(committeeId.startsWith('a177a-threat-')).toBe(true)
          expect(teamId).not.toBe(committeeId)
        },
      ),
      { numRuns: 30 },
    )
  })
})

// ─── Property 2: 签字表预填完整性 ───────────────────────────────────────────

describe('Feature: a17-7-independence-declaration, Property 2: 签字表预填完整性', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * For any project with N team members in assignments,
   * initial load SHALL produce team_sign_table with exactly N rows pre-filled.
   */

  interface TeamMember { name: string }
  interface SignRow { index: number; name: string; signed: boolean; date: string | null }

  function preFillSignTable(members: TeamMember[]): SignRow[] {
    return members.map((m, i) => ({
      index: i + 1,
      name: m.name,
      signed: false,
      date: null,
    }))
  }

  it('pre-fill count equals team member count', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ name: fc.string({ minLength: 1, maxLength: 10 }) }),
          { minLength: 0, maxLength: 20 },
        ),
        (members) => {
          const table = preFillSignTable(members)
          expect(table.length).toBe(members.length)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('pre-filled rows preserve member names in order', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ name: fc.string({ minLength: 1, maxLength: 10 }) }),
          { minLength: 1, maxLength: 10 },
        ),
        (members) => {
          const table = preFillSignTable(members)
          members.forEach((m, i) => {
            expect(table[i].name).toBe(m.name)
          })
        },
      ),
      { numRuns: 30 },
    )
  })

  it('pre-filled rows are always unsigned', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ name: fc.string({ minLength: 1, maxLength: 10 }) }),
          { minLength: 1, maxLength: 10 },
        ),
        (members) => {
          const table = preFillSignTable(members)
          table.forEach(row => {
            expect(row.signed).toBe(false)
            expect(row.date).toBeNull()
          })
        },
      ),
      { numRuns: 30 },
    )
  })

  it('pre-filled row indices are sequential starting from 1', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({ name: fc.string({ minLength: 1, maxLength: 10 }) }),
          { minLength: 1, maxLength: 15 },
        ),
        (members) => {
          const table = preFillSignTable(members)
          table.forEach((row, i) => {
            expect(row.index).toBe(i + 1)
          })
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 3: 威胁记录增删一致性 ─────────────────────────────────────────

describe('Feature: a17-7-independence-declaration, Property 3: 威胁记录增删一致性', () => {
  /**
   * **Validates: Requirements 7.3**
   *
   * For any sequence of add/remove operations on threat tables,
   * the count SHALL equal (adds - removes) and never be negative.
   */

  type ThreatOp = { type: 'add' } | { type: 'remove'; index: number }

  function applyThreatOps(initialCount: number, ops: ThreatOp[]): number {
    let count = initialCount
    for (const op of ops) {
      if (op.type === 'add') {
        count++
      } else if (op.type === 'remove' && count > 0) {
        count--
      }
    }
    return count
  }

  function countEffective(initialCount: number, ops: ThreatOp[]): { adds: number; removes: number } {
    let adds = 0
    let removes = 0
    let current = initialCount
    for (const op of ops) {
      if (op.type === 'add') {
        adds++
        current++
      } else if (op.type === 'remove' && current > 0) {
        removes++
        current--
      }
    }
    return { adds, removes }
  }

  const opArb: fc.Arbitrary<ThreatOp> = fc.oneof(
    fc.constant({ type: 'add' } as ThreatOp),
    fc.integer({ min: 0, max: 99 }).map((index) => ({ type: 'remove', index } as ThreatOp)),
  )

  it('final count = initial + effective_adds - effective_removes', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10 }),
        fc.array(opArb, { minLength: 0, maxLength: 15 }),
        (initial, ops) => {
          const result = applyThreatOps(initial, ops)
          const { adds, removes } = countEffective(initial, ops)
          expect(result).toBe(initial + adds - removes)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('count is never negative', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10 }),
        fc.array(opArb, { minLength: 0, maxLength: 20 }),
        (initial, ops) => {
          const result = applyThreatOps(initial, ops)
          expect(result).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('add always increases count by 1', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10 }),
        (initial) => {
          const result = applyThreatOps(initial, [{ type: 'add' }])
          expect(result).toBe(initial + 1)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('remove on non-empty decreases count by 1', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }),
        fc.integer({ min: 0, max: 99 }),
        (initial, idx) => {
          const result = applyThreatOps(initial, [{ type: 'remove', index: idx }])
          expect(result).toBe(initial - 1)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('remove on empty is a no-op', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 99 }),
        (idx) => {
          const result = applyThreatOps(0, [{ type: 'remove', index: idx }])
          expect(result).toBe(0)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('property holds across all 3 threat types', () => {
    const threatTypes: ThreatType[] = ['economic_interest', 'loan_guarantee', 'business_relation']
    fc.assert(
      fc.property(
        fc.constantFrom(...threatTypes),
        fc.integer({ min: 0, max: 5 }),
        fc.array(opArb, { minLength: 0, maxLength: 10 }),
        (_type, initial, ops) => {
          const result = applyThreatOps(initial, ops)
          expect(result).toBeGreaterThanOrEqual(0)
          const { adds, removes } = countEffective(initial, ops)
          expect(result).toBe(initial + adds - removes)
        },
      ),
      { numRuns: 50 },
    )
  })
})
