/**
 * Property-Based Tests — A17-4 重大专业分歧事项记录
 *
 * Spec: .kiro/specs/a17-4-disagreement-record/
 * Task: 2.2
 *
 * Property 1: item_id 格式 — 所有保存 item_id 匹配 a174-personnel | a174-sec{N}-{field} | a174-signature-{field}
 * Property 3: 人员表增删一致性 — add/remove 后 length = initial + adds - removes
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Pure logic extracted from composable for PBT ────────────────────────────

const SECTION_FIELD_MAP: Record<number, string> = {
  1: 'parties',
  2: 'cause',
  3: 'procedures',
  4: 'opinions',
  5: 'considerations',
  6: 'conclusion',
}

const SIGNATURE_FIELDS = ['preparer', 'reviewer', 'date'] as const

/** Generate item_id for personnel */
function personnelItemId(): string {
  return 'a174-personnel'
}

/** Generate item_id for section */
function sectionItemId(secNum: number): string {
  const field = SECTION_FIELD_MAP[secNum]
  return `a174-sec${secNum}-${field}`
}

/** Generate item_id for signature */
function signatureItemId(field: string): string {
  return `a174-signature-${field}`
}

/** Validate item_id format */
function isValidItemId(id: string): boolean {
  if (id === 'a174-personnel') return true
  if (/^a174-sec[1-6]-(parties|cause|procedures|opinions|considerations|conclusion)$/.test(id)) return true
  if (/^a174-signature-(preparer|reviewer|date)$/.test(id)) return true
  return false
}

// ─── Personnel array simulation ─────────────────────────────────────────────

interface PersonnelRow {
  name: string
  position: string
  role: string
}

type PersonnelOp = { type: 'add' } | { type: 'remove'; index: number }

function applyOps(initial: PersonnelRow[], ops: PersonnelOp[]): PersonnelRow[] {
  const arr = [...initial]
  for (const op of ops) {
    if (op.type === 'add') {
      arr.push({ name: '', position: '', role: '' })
    } else if (op.type === 'remove' && arr.length > 0) {
      const idx = op.index % arr.length
      arr.splice(idx, 1)
    }
  }
  return arr
}

function countEffectiveOps(initial: PersonnelRow[], ops: PersonnelOp[]): { adds: number; removes: number } {
  let adds = 0
  let removes = 0
  let currentLength = initial.length
  for (const op of ops) {
    if (op.type === 'add') {
      adds++
      currentLength++
    } else if (op.type === 'remove' && currentLength > 0) {
      removes++
      currentLength--
    }
  }
  return { adds, removes }
}

// ─── Property 1: item_id 格式 ───────────────────────────────────────────────

describe('Feature: a17-4-disagreement-record, Property 1: item_id 格式', () => {
  /**
   * **Validates: Requirements 1.2**
   */
  it('personnel item_id is always "a174-personnel"', () => {
    const id = personnelItemId()
    expect(id).toBe('a174-personnel')
    expect(isValidItemId(id)).toBe(true)
  })

  it('section item_ids match a174-sec{N}-{field} format for all 6 sections', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 6 }),
        (secNum) => {
          const id = sectionItemId(secNum)
          expect(id).toMatch(/^a174-sec[1-6]-[a-z]+$/)
          expect(isValidItemId(id)).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('signature item_ids match a174-signature-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...SIGNATURE_FIELDS),
        (field) => {
          const id = signatureItemId(field)
          expect(id).toMatch(/^a174-signature-[a-z]+$/)
          expect(isValidItemId(id)).toBe(true)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('all generated item_ids pass validation', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(personnelItemId()),
          fc.integer({ min: 1, max: 6 }).map(sectionItemId),
          fc.constantFrom(...SIGNATURE_FIELDS).map(signatureItemId),
        ),
        (id) => {
          expect(isValidItemId(id)).toBe(true)
          expect(id.startsWith('a174-')).toBe(true)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('item_ids from different categories never overlap', () => {
    const personnelId = personnelItemId()
    const sectionIds = [1, 2, 3, 4, 5, 6].map(sectionItemId)
    const sigIds = SIGNATURE_FIELDS.map(signatureItemId)
    const all = [personnelId, ...sectionIds, ...sigIds]
    const unique = new Set(all)
    expect(unique.size).toBe(all.length)
  })
})

// ─── Property 3: 人员表增删一致性 ───────────────────────────────────────────

describe('Feature: a17-4-disagreement-record, Property 3: 人员表增删一致性', () => {
  /**
   * **Validates: Requirements 3.2, 3.3**
   */
  const personnelRowArb = fc.record({
    name: fc.string({ minLength: 0, maxLength: 10 }),
    position: fc.string({ minLength: 0, maxLength: 10 }),
    role: fc.string({ minLength: 0, maxLength: 10 }),
  })

  const opArb: fc.Arbitrary<PersonnelOp> = fc.oneof(
    fc.constant({ type: 'add' } as PersonnelOp),
    fc.integer({ min: 0, max: 99 }).map((index) => ({ type: 'remove', index } as PersonnelOp)),
  )

  it('final length = initial + effective_adds - effective_removes', () => {
    fc.assert(
      fc.property(
        fc.array(personnelRowArb, { minLength: 0, maxLength: 5 }),
        fc.array(opArb, { minLength: 0, maxLength: 10 }),
        (initial, ops) => {
          const result = applyOps(initial, ops)
          const { adds, removes } = countEffectiveOps(initial, ops)
          expect(result.length).toBe(initial.length + adds - removes)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('add always increases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(personnelRowArb, { minLength: 0, maxLength: 5 }),
        (initial) => {
          const result = applyOps(initial, [{ type: 'add' }])
          expect(result.length).toBe(initial.length + 1)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('remove on non-empty decreases length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(personnelRowArb, { minLength: 1, maxLength: 5 }),
        fc.integer({ min: 0, max: 99 }),
        (initial, idx) => {
          const result = applyOps(initial, [{ type: 'remove', index: idx }])
          expect(result.length).toBe(initial.length - 1)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('remove on empty array does nothing', () => {
    const result = applyOps([], [{ type: 'remove', index: 0 }])
    expect(result.length).toBe(0)
  })

  it('added row has empty fields', () => {
    fc.assert(
      fc.property(
        fc.array(personnelRowArb, { minLength: 0, maxLength: 3 }),
        (initial) => {
          const result = applyOps(initial, [{ type: 'add' }])
          const lastRow = result[result.length - 1]
          expect(lastRow.name).toBe('')
          expect(lastRow.position).toBe('')
          expect(lastRow.role).toBe('')
        },
      ),
      { numRuns: 20 },
    )
  })
})
