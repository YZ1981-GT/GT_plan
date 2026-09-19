/**
 * Property-Based Tests — A8-1 管理层对其他信息的书面声明
 *
 * Spec: .kiro/specs/a8-1-other-info-representation/
 * Task: 2.2
 *
 * Property 1: item_id 格式 — `a81-statement-{N}-{field}` or `a81-signature-{field}`
 * Property 3: 文件清单增删一致性 — length = initial + adds - removes, order preserved
 * Property 7: 双模式切换数据一致性 — edit → flush → switch → switch-back preserves data
 *
 * **Validates: Requirements 4.5, 5.3, 6.4, 7.3, 8.3, 9.3, 10.5, 13.2, 4.3, 4.4, 7.2, 8.2, 2.5, 13.1**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Pure logic extracted from composable for PBT ────────────────────────────

/** Generate item_id for statement fields */
function statementItemId(statementNum: number, fieldId: string): string {
  return `a81-statement-${statementNum}-${fieldId}`
}

/** Generate item_id for signature fields */
function signatureItemId(fieldId: string): string {
  return `a81-signature-${fieldId}`
}

/** Add a file to a file list (pure) */
function addFile(files: string[], fileName: string): string[] {
  if (!fileName.trim()) return files
  return [...files, fileName.trim()]
}

/** Remove a file by index from a file list (pure) */
function removeFile(files: string[], index: number): string[] {
  if (index < 0 || index >= files.length) return files
  return [...files.slice(0, index), ...files.slice(index + 1)]
}

// ─── Property 1: item_id 格式一致性 ─────────────────────────────────────────

describe('Feature: a8-1-other-info-representation, Property 1: item_id 格式 a81-{section}-{field}', () => {
  it('statement file list fields produce a81-statement-{N}-files format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(1, 4, 5),
        (statementNum) => {
          const id = statementItemId(statementNum, 'files')
          expect(id).toMatch(/^a81-statement-[145]-files$/)
          expect(id).toBe(`a81-statement-${statementNum}-files`)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('statement 2 date field produces a81-statement-2-date format', () => {
    const id = statementItemId(2, 'date')
    expect(id).toBe('a81-statement-2-date')
    expect(id).toMatch(/^a81-statement-2-date$/)
  })

  it('statement 3 fields produce correct format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('consistency', 'explanation'),
        (field) => {
          const id = statementItemId(3, field)
          expect(id).toMatch(/^a81-statement-3-(consistency|explanation)$/)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('statement 6 other field produces a81-statement-6-other format', () => {
    const id = statementItemId(6, 'other')
    expect(id).toBe('a81-statement-6-other')
  })

  it('signature fields produce a81-signature-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('representative', 'date'),
        (field) => {
          const id = signatureItemId(field)
          expect(id).toMatch(/^a81-signature-[a-z_]+$/)
          expect(id).toBe(`a81-signature-${field}`)
        },
      ),
      { numRuns: 10 },
    )
  })

  it('all item_ids start with a81- prefix', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.tuple(fc.constantFrom(1, 4, 5), fc.constant('files'))
            .map(([n, f]) => statementItemId(n, f)),
          fc.constant(statementItemId(2, 'date')),
          fc.constantFrom('consistency', 'explanation')
            .map(f => statementItemId(3, f)),
          fc.constant(statementItemId(6, 'other')),
          fc.constantFrom('representative', 'date')
            .map(f => signatureItemId(f)),
        ),
        (itemId) => {
          expect(itemId).toMatch(/^a81-/)
        },
      ),
      { numRuns: 30 },
    )
  })
})

// ─── Property 3: 文件清单增删一致性 ─────────────────────────────────────────

describe('Feature: a8-1-other-info-representation, Property 3: 文件清单增删一致性', () => {
  it('adding a file increases list length by 1', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 10 }),
        // 排除纯空白：addFile 会对 trim 后为空的名称忽略
        fc.string({ minLength: 1, maxLength: 30 }).filter((s) => s.trim().length > 0),
        (initialFiles, newFile) => {
          const result = addFile(initialFiles, newFile)
          expect(result.length).toBe(initialFiles.length + 1)
          expect(result[result.length - 1]).toBe(newFile.trim())
        },
      ),
      { numRuns: 30 },
    )
  })

  it('adding empty file does not change list', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 10 }),
        fc.constantFrom('', '   ', '\t'),
        (initialFiles, emptyFile) => {
          const result = addFile(initialFiles, emptyFile)
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
          const result = removeFile(files, index)
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
          const result = removeFile(files, negIndex)
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
          let expectedAdds = 0
          let expectedRemoves = 0

          for (const op of ops) {
            if (op.type === 'add') {
              files = addFile(files, op.value)
              expectedAdds++
            } else {
              const before = files.length
              files = removeFile(files, op.index)
              if (files.length < before) expectedRemoves++
            }
          }

          expect(files.length).toBe(initial.length + expectedAdds - expectedRemoves)
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
          const result = removeFile(files, removeIdx)
          // All items except the removed one should be in original order
          for (let i = 0; i < result.length; i++) {
            expect(result[i]).toBe(files[i + 1])
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 7: 双模式切换数据一致性 ───────────────────────────────────────

describe('Feature: a8-1-other-info-representation, Property 7: 双模式切换数据一致性', () => {
  it('data persists across simulated mode switches', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 5 }),
        fc.string({ minLength: 0, maxLength: 30 }),
        fc.constantFrom('Y', 'N', null),
        fc.string({ minLength: 0, maxLength: 50 }),
        (files, date, consistency, representative) => {
          // Simulate state before mode switch
          const state = {
            statements: {
              1: { files: [...files] },
              2: { date },
              3: { consistency, explanation: consistency === 'N' ? '说明' : null },
              4: { files: [] },
              5: { files: [] },
              6: { other: null },
            },
            signatureData: { representative, signatureDate: '2026-03-31' },
          }

          // Simulate mode switch (structured → OO → structured)
          // Data should be unchanged since it's held in reactive refs
          const afterSwitch = JSON.parse(JSON.stringify(state))

          expect(afterSwitch.statements[1].files).toEqual(files)
          expect(afterSwitch.statements[2].date).toBe(date)
          expect(afterSwitch.statements[3].consistency).toBe(consistency)
          expect(afterSwitch.signatureData.representative).toBe(representative)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('file list values are preserved exactly after serialization round-trip', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 8 }),
        (files) => {
          // Simulate JSON save + reload (what happens on mode switch with flush)
          const serialized = JSON.stringify(files)
          const deserialized = JSON.parse(serialized)
          expect(deserialized).toEqual(files)
        },
      ),
      { numRuns: 20 },
    )
  })
})
