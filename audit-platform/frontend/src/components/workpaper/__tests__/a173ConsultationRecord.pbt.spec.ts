/**
 * Property-Based Tests — A17-3 业务咨询记录
 *
 * Spec: .kiro/specs/a17-3-consultation-record/
 * Task: 2.2
 *
 * Property 1: item_id 格式 — `a173-meta-{field}` or `a173-sec{N}-{field}`
 * Property 2: 文件 tag 增删一致性 — length = initial + adds - removes, order preserved
 *
 * **Validates: Requirements 4.4, 8.3, 9.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Pure logic extracted from composable for PBT ────────────────────────────

/** Generate item_id for meta fields */
function metaItemId(field: string): string {
  return `a173-meta-${field}`
}

/** Generate item_id for section fields */
function sectionItemId(secNum: number, field: string): string {
  return `a173-sec${secNum}-${field}`
}

/** Add a file tag (pure) */
function addFileTag(files: string[], fileName: string): string[] {
  const trimmed = fileName.trim()
  if (!trimmed) return files
  return [...files, trimmed]
}

/** Remove a file tag by index (pure) */
function removeFileTag(files: string[], index: number): string[] {
  if (index < 0 || index >= files.length) return files
  return [...files.slice(0, index), ...files.slice(index + 1)]
}

// ─── Property 1: item_id 格式一致性 ─────────────────────────────────────────

describe('Feature: a17-3-consultation-record, Property 1: item_id 格式 a173-{section}-{field}', () => {
  it('meta fields produce a173-meta-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('department', 'client_name', 'consult_type', 'period'),
        (field) => {
          const id = metaItemId(field)
          expect(id).toMatch(/^a173-meta-[a-z_]+$/)
          expect(id).toBe(`a173-meta-${field}`)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('section 1 fields produce a173-sec1-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('overview', 'background', 'files'),
        (field) => {
          const id = sectionItemId(1, field)
          expect(id).toMatch(/^a173-sec1-[a-z_]+$/)
          expect(id).toBe(`a173-sec1-${field}`)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('section 2 opinion produces a173-sec2-opinion format', () => {
    const id = sectionItemId(2, 'opinion')
    expect(id).toBe('a173-sec2-opinion')
  })

  it('section 3 fields produce a173-sec3-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('standards', 'reply'),
        (field) => {
          const id = sectionItemId(3, field)
          expect(id).toMatch(/^a173-sec3-[a-z_]+$/)
          expect(id).toBe(`a173-sec3-${field}`)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('section 4 opinion produces a173-sec4-opinion format', () => {
    const id = sectionItemId(4, 'opinion')
    expect(id).toBe('a173-sec4-opinion')
  })

  it('all item_ids start with a173- prefix', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constantFrom('department', 'client_name', 'consult_type', 'period')
            .map(f => metaItemId(f)),
          fc.constantFrom('overview', 'background', 'files')
            .map(f => sectionItemId(1, f)),
          fc.constant(sectionItemId(2, 'opinion')),
          fc.constantFrom('standards', 'reply')
            .map(f => sectionItemId(3, f)),
          fc.constant(sectionItemId(4, 'opinion')),
        ),
        (itemId) => {
          expect(itemId).toMatch(/^a173-/)
        },
      ),
      { numRuns: 30 },
    )
  })
})

// ─── Property 2: 文件 tag 增删一致性 ────────────────────────────────────────

describe('Feature: a17-3-consultation-record, Property 2: 文件 tag 增删一致性', () => {
  it('adding a file tag increases list length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 10 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        (initialFiles, newFile) => {
          const result = addFileTag(initialFiles, newFile)
          expect(result.length).toBe(initialFiles.length + 1)
          expect(result[result.length - 1]).toBe(newFile.trim())
        },
      ),
      { numRuns: 30 },
    )
  })

  it('adding empty/whitespace file tag does not change list', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 10 }),
        fc.constantFrom('', '   ', '\t', '  \n  '),
        (initialFiles, emptyFile) => {
          const result = addFileTag(initialFiles, emptyFile)
          expect(result.length).toBe(initialFiles.length)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('removing a valid index decreases list length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 1, maxLength: 10 }),
        (files) => {
          const index = Math.floor(Math.random() * files.length)
          const result = removeFileTag(files, index)
          expect(result.length).toBe(files.length - 1)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('removing invalid index does not change list', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 10 }),
        fc.integer({ min: -10, max: -1 }),
        (files, negIndex) => {
          const result = removeFileTag(files, negIndex)
          expect(result).toEqual(files)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('sequence of adds and removes yields correct final length', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 5 }),
        fc.array(
          fc.oneof(
            fc.string({ minLength: 1, maxLength: 20 }).map(s => ({ type: 'add' as const, value: s })),
            fc.nat({ max: 20 }).map(i => ({ type: 'remove' as const, index: i })),
          ),
          { minLength: 1, maxLength: 10 },
        ),
        (initial, ops) => {
          let files = [...initial]
          let adds = 0
          let removes = 0

          for (const op of ops) {
            if (op.type === 'add') {
              files = addFileTag(files, op.value)
              adds++
            } else {
              const before = files.length
              files = removeFileTag(files, op.index)
              if (files.length < before) removes++
            }
          }

          expect(files.length).toBe(initial.length + adds - removes)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('order of remaining items is preserved after removal', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 2, maxLength: 8 }),
        (files) => {
          const removeIdx = 0
          const result = removeFileTag(files, removeIdx)
          for (let i = 0; i < result.length; i++) {
            expect(result[i]).toBe(files[i + 1])
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('file tag JSON round-trip preserves content', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 8 }),
        (files) => {
          const serialized = JSON.stringify(files)
          const deserialized = JSON.parse(serialized)
          expect(deserialized).toEqual(files)
        },
      ),
      { numRuns: 20 },
    )
  })
})
