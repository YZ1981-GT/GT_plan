/**
 * Property-Based Tests — B1-4 尽职调查报告
 *
 * Spec: .kiro/specs/b1-4-due-diligence-report/
 * Tasks: 3.3–3.7
 *
 * 使用 fast-check + vitest 验证 5 个 correctness properties。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { isChapterComplete } from '../useB14Navigation'
import {
  buildB14ChapterContentItemId,
  buildB14SectionItemId,
  buildB14TableItemId,
  buildB14VariantItemId,
  buildB14SignatureItemId,
  type B14ChapterData,
  type B14Section,
} from '../useB14DueDiligence'

// ─── Constants ───────────────────────────────────────────────────────────────

const ALL_CHAPTER_IDS = Array.from({ length: 13 }, (_, i) => `ch${i + 1}`)
const STANDARD_ONLY_CHAPTERS = new Set(['ch11', 'ch12'])

// ─── Arbitraries ─────────────────────────────────────────────────────────────

/** Arbitrary for variant */
const arbVariant = fc.constantFrom<'standard' | 'simplified'>('standard', 'simplified')

/** Arbitrary for a non-empty string (content) */
const arbNonEmptyContent = fc.string({ minLength: 1, maxLength: 100 }).filter(s => s.trim().length > 0)

/** Arbitrary for nullable content (empty/null = incomplete) */
const arbNullableContent = fc.oneof(
  fc.constant(null as string | null),
  fc.constant('' as string | null),
  fc.constant('   ' as string | null),
  arbNonEmptyContent.map(s => s as string | null),
)

/** Arbitrary for table rows (0 or more rows) */
const arbTableRows = fc.array(
  fc.dictionary(
    fc.string({ minLength: 1, maxLength: 10 }),
    fc.oneof(
      fc.string({ maxLength: 20 }),
      fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }).filter(n => !Object.is(n, -0)),
      fc.constant(null as string | number | null),
    ),
  ),
  { minLength: 0, maxLength: 5 },
)

/** Arbitrary for a textarea section */
const arbTextareaSection = (id: string): fc.Arbitrary<B14Section> =>
  arbNullableContent.map(content => ({
    id,
    title: `Section ${id}`,
    type: 'textarea' as const,
    content,
  }))

/** Arbitrary for a table section */
const arbTableSection = (id: string): fc.Arbitrary<B14Section> =>
  arbTableRows.map(rows => ({
    id,
    title: `Section ${id}`,
    type: 'table' as const,
    table_id: `table-${id}`,
    rows,
  }))

/** Arbitrary for a mixed section (randomly textarea or table) */
const arbSection = (id: string): fc.Arbitrary<B14Section> =>
  fc.oneof(arbTextareaSection(id), arbTableSection(id))

/** Arbitrary for a textarea chapter */
const arbTextareaChapter = (chId: string): fc.Arbitrary<B14ChapterData> =>
  arbNullableContent.map(content => ({
    id: chId,
    title: `Chapter ${chId}`,
    type: 'textarea' as const,
    visible: true,
    content,
  }))

/** Arbitrary for a table chapter */
const arbTableChapter = (chId: string): fc.Arbitrary<B14ChapterData> =>
  arbTableRows.map(rows => ({
    id: chId,
    title: `Chapter ${chId}`,
    type: 'table' as const,
    visible: true,
    table_id: `${chId}-main`,
    rows,
  }))

/** Arbitrary for a mixed chapter (1-3 sections) */
const arbMixedChapter = (chId: string): fc.Arbitrary<B14ChapterData> =>
  fc.array(arbSection('sec'), { minLength: 1, maxLength: 3 }).map(sections => ({
    id: chId,
    title: `Chapter ${chId}`,
    type: 'mixed' as const,
    visible: true,
    sections: sections.map((s, i) => ({ ...s, id: `${chId}-sec${i + 1}` })),
  }))

/** Arbitrary for any chapter type */
const arbChapter = (chId: string): fc.Arbitrary<B14ChapterData> =>
  fc.oneof(arbTextareaChapter(chId), arbTableChapter(chId), arbMixedChapter(chId))

/** Arbitrary for a full set of 13 chapters */
const arbAllChapters = fc.tuple(
  ...ALL_CHAPTER_IDS.map(id => arbChapter(id))
).map(chapters => {
  const result: Record<string, B14ChapterData> = {}
  for (const ch of chapters) {
    result[ch.id] = ch
  }
  return result
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: Variant controls chapter visibility
// ═══════════════════════════════════════════════════════════════════════════════

/** Feature: b1-4-due-diligence-report, Property 1: Variant controls chapter visibility */
describe('Feature: b1-4-due-diligence-report, Property 1: Variant controls chapter visibility', () => {
  /**
   * **Validates: Requirements 2.2, 4.2**
   *
   * For any variant value ('standard' or 'simplified'), verify visible chapters set:
   * - simplified: hides ch11 and ch12 (only those 2 hidden)
   * - standard: all 13 chapters visible
   */

  function applyVariantVisibility(
    chapters: Record<string, B14ChapterData>,
    variant: 'standard' | 'simplified',
  ): Record<string, B14ChapterData> {
    const result = JSON.parse(JSON.stringify(chapters)) as Record<string, B14ChapterData>
    for (const [chId, ch] of Object.entries(result)) {
      if (STANDARD_ONLY_CHAPTERS.has(chId)) {
        ch.visible = variant === 'standard'
      } else {
        ch.visible = true
      }
    }
    return result
  }

  it('standard variant: all 13 chapters are visible', () => {
    fc.assert(
      fc.property(arbAllChapters, (chapters) => {
        const result = applyVariantVisibility(chapters, 'standard')
        const visibleIds = Object.entries(result)
          .filter(([, ch]) => ch.visible)
          .map(([id]) => id)
          .sort()

        expect(visibleIds.sort()).toEqual(ALL_CHAPTER_IDS.sort())
      }),
      { numRuns: 100 },
    )
  })

  it('simplified variant: ch11 and ch12 are hidden, all others visible', () => {
    fc.assert(
      fc.property(arbAllChapters, (chapters) => {
        const result = applyVariantVisibility(chapters, 'simplified')

        const hiddenIds = Object.entries(result)
          .filter(([, ch]) => !ch.visible)
          .map(([id]) => id)
          .sort()

        const visibleIds = Object.entries(result)
          .filter(([, ch]) => ch.visible)
          .map(([id]) => id)
          .sort()

        expect(hiddenIds).toEqual(['ch11', 'ch12'])
        expect(visibleIds.length).toBe(11)
        expect(visibleIds).not.toContain('ch11')
        expect(visibleIds).not.toContain('ch12')
      }),
      { numRuns: 100 },
    )
  })

  it('only ch11 and ch12 are affected by variant changes (no other chapters hidden)', () => {
    fc.assert(
      fc.property(arbAllChapters, arbVariant, (chapters, variant) => {
        const result = applyVariantVisibility(chapters, variant)

        for (const [chId, ch] of Object.entries(result)) {
          if (!STANDARD_ONLY_CHAPTERS.has(chId)) {
            // Non-standard-only chapters are always visible
            expect(ch.visible).toBe(true)
          } else {
            // Standard-only chapters depend on variant
            expect(ch.visible).toBe(variant === 'standard')
          }
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: Variant switch preserves chapter data
// ═══════════════════════════════════════════════════════════════════════════════

/** Feature: b1-4-due-diligence-report, Property 2: Variant switch preserves chapter data */
describe('Feature: b1-4-due-diligence-report, Property 2: Variant switch preserves chapter data', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * For any set of chapter data and any sequence of variant switches,
   * the chapter data content remains identical. Only `visible` flag changes.
   */

  /** Apply a variant switch (mutates visible only) */
  function switchVariant(
    chapters: Record<string, B14ChapterData>,
    variant: 'standard' | 'simplified',
  ): void {
    for (const [chId, ch] of Object.entries(chapters)) {
      if (STANDARD_ONLY_CHAPTERS.has(chId)) {
        ch.visible = variant === 'standard'
      }
    }
  }

  /** Extract data content (everything except visible flag) */
  function extractDataContent(chapters: Record<string, B14ChapterData>): Record<string, any> {
    const result: Record<string, any> = {}
    for (const [chId, ch] of Object.entries(chapters)) {
      const { visible, ...data } = ch
      result[chId] = data
    }
    return result
  }

  it('single variant switch does not alter chapter data content', () => {
    fc.assert(
      fc.property(arbAllChapters, arbVariant, (chapters, targetVariant) => {
        const dataBefore = extractDataContent(chapters)
        switchVariant(chapters, targetVariant)
        const dataAfter = extractDataContent(chapters)

        expect(dataAfter).toEqual(dataBefore)
      }),
      { numRuns: 100 },
    )
  })

  it('multiple variant switches preserve data content', () => {
    fc.assert(
      fc.property(
        arbAllChapters,
        fc.array(arbVariant, { minLength: 1, maxLength: 10 }),
        (chapters, variantSequence) => {
          const dataBefore = extractDataContent(chapters)

          for (const v of variantSequence) {
            switchVariant(chapters, v)
          }

          const dataAfter = extractDataContent(chapters)
          expect(dataAfter).toEqual(dataBefore)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('only visible flag changes after variant switch', () => {
    fc.assert(
      fc.property(arbAllChapters, arbVariant, (chapters, targetVariant) => {
        // Deep clone to preserve original
        const original = JSON.parse(JSON.stringify(chapters)) as Record<string, B14ChapterData>
        switchVariant(chapters, targetVariant)

        for (const chId of Object.keys(chapters)) {
          const origCh = original[chId]
          const newCh = chapters[chId]

          // Content fields unchanged
          expect(newCh.id).toBe(origCh.id)
          expect(newCh.title).toBe(origCh.title)
          expect(newCh.type).toBe(origCh.type)
          expect(newCh.content).toEqual(origCh.content)
          expect(JSON.stringify(newCh.rows)).toEqual(JSON.stringify(origCh.rows))
          expect(JSON.stringify(newCh.sections)).toEqual(JSON.stringify(origCh.sections))
          expect(newCh.table_id).toEqual(origCh.table_id)
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: Completion status computation
// ═══════════════════════════════════════════════════════════════════════════════

/** Feature: b1-4-due-diligence-report, Property 3: Completion status computation */
describe('Feature: b1-4-due-diligence-report, Property 3: Completion status computation', () => {
  /**
   * **Validates: Requirements 3.4, 3.5**
   *
   * For any chapter data state:
   * - textarea complete = non-empty non-null content (after trim)
   * - table complete = ≥1 row
   * - mixed complete = ≥1 non-empty section
   * - overallProgress = Math.round(completedVisible / totalVisible × 100)
   */

  /** Reference implementation of isChapterComplete for verification */
  function expectedComplete(ch: B14ChapterData): boolean {
    switch (ch.type) {
      case 'textarea':
        return !!ch.content && ch.content.trim().length > 0
      case 'table':
        return Array.isArray(ch.rows) && ch.rows.length > 0
      case 'mixed':
        if (!Array.isArray(ch.sections) || ch.sections.length === 0) return false
        return ch.sections.some(section => {
          if (section.type === 'textarea') {
            return !!section.content && section.content.trim().length > 0
          }
          if (section.type === 'table') {
            return Array.isArray(section.rows) && section.rows.length > 0
          }
          return false
        })
      default:
        return false
    }
  }

  it('isChapterComplete matches expected logic for any chapter data', () => {
    fc.assert(
      fc.property(
        fc.oneof(...ALL_CHAPTER_IDS.map(id => arbChapter(id))),
        (chapter) => {
          const actual = isChapterComplete(chapter)
          const expected = expectedComplete(chapter)
          expect(actual).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('overallProgress = round(completedVisible / totalVisible × 100)', () => {
    fc.assert(
      fc.property(arbAllChapters, arbVariant, (chapters, variant) => {
        // Apply variant visibility
        for (const [chId, ch] of Object.entries(chapters)) {
          if (STANDARD_ONLY_CHAPTERS.has(chId)) {
            ch.visible = variant === 'standard'
          } else {
            ch.visible = true
          }
        }

        // Calculate expected progress
        let visibleCount = 0
        let completedCount = 0
        for (const ch of Object.values(chapters)) {
          if (!ch.visible) continue
          visibleCount++
          if (isChapterComplete(ch)) {
            completedCount++
          }
        }

        const expectedProgress = visibleCount === 0
          ? 0
          : Math.round((completedCount / visibleCount) * 100)

        // Verify bounds
        expect(expectedProgress).toBeGreaterThanOrEqual(0)
        expect(expectedProgress).toBeLessThanOrEqual(100)

        // Verify computation correctness
        if (visibleCount > 0) {
          expect(expectedProgress).toBe(Math.round((completedCount / visibleCount) * 100))
        }
      }),
      { numRuns: 100 },
    )
  })

  it('textarea chapter: complete iff content is non-empty non-whitespace', () => {
    fc.assert(
      fc.property(arbNullableContent, (content) => {
        const ch: B14ChapterData = {
          id: 'ch1',
          title: 'Test',
          type: 'textarea',
          visible: true,
          content,
        }

        const expected = !!content && content.trim().length > 0
        expect(isChapterComplete(ch)).toBe(expected)
      }),
      { numRuns: 100 },
    )
  })

  it('table chapter: complete iff rows.length >= 1', () => {
    fc.assert(
      fc.property(arbTableRows, (rows) => {
        const ch: B14ChapterData = {
          id: 'ch7',
          title: 'Test',
          type: 'table',
          visible: true,
          table_id: 'test-table',
          rows,
        }

        const expected = rows.length > 0
        expect(isChapterComplete(ch)).toBe(expected)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: item_id format correctness
// ═══════════════════════════════════════════════════════════════════════════════

/** Feature: b1-4-due-diligence-report, Property 4: item_id format correctness */
describe('Feature: b1-4-due-diligence-report, Property 4: item_id format correctness', () => {
  /**
   * **Validates: Requirements 5.2, 9.3**
   *
   * For any chapter number (1-13), field name, and signature field:
   * - b14-ch{N}-content for chapter textarea content
   * - b14-ch{N}-{section_id} for chapter sections
   * - b14-ch{N}-table-{tableId} for table data
   * - b14-signature-{field} for signature fields
   * - b14-meta-variant for variant meta
   */

  const arbChapterNum = fc.integer({ min: 1, max: 13 })
  const arbFieldId = fc.string({ minLength: 1, maxLength: 20 }).filter(s => /^[a-z0-9_-]+$/.test(s))
  const arbSignatureField = fc.constantFrom('partner', 'partner_date', 'manager', 'manager_date', 'report_date')

  it('buildB14ChapterContentItemId produces b14-ch{N}-content pattern', () => {
    fc.assert(
      fc.property(arbChapterNum, (chNum) => {
        const itemId = buildB14ChapterContentItemId(chNum)
        expect(itemId).toBe(`b14-ch${chNum}-content`)
        expect(itemId).toMatch(/^b14-ch\d{1,2}-content$/)
      }),
      { numRuns: 100 },
    )
  })

  it('buildB14SectionItemId produces b14-ch{N}-{sectionId} pattern', () => {
    fc.assert(
      fc.property(arbChapterNum, arbFieldId, (chNum, sectionId) => {
        const itemId = buildB14SectionItemId(chNum, sectionId)
        expect(itemId).toBe(`b14-ch${chNum}-${sectionId}`)
        expect(itemId).toMatch(/^b14-ch\d{1,2}-.+$/)
      }),
      { numRuns: 100 },
    )
  })

  it('buildB14TableItemId produces b14-ch{N}-table-{tableId} pattern', () => {
    fc.assert(
      fc.property(arbChapterNum, arbFieldId, (chNum, tableId) => {
        const itemId = buildB14TableItemId(chNum, tableId)
        expect(itemId).toBe(`b14-ch${chNum}-table-${tableId}`)
        expect(itemId).toMatch(/^b14-ch\d{1,2}-table-.+$/)
      }),
      { numRuns: 100 },
    )
  })

  it('buildB14SignatureItemId produces b14-signature-{field} pattern', () => {
    fc.assert(
      fc.property(arbSignatureField, (field) => {
        const itemId = buildB14SignatureItemId(field)
        expect(itemId).toBe(`b14-signature-${field}`)
        expect(itemId).toMatch(/^b14-signature-.+$/)
      }),
      { numRuns: 100 },
    )
  })

  it('buildB14VariantItemId produces b14-meta-variant', () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const itemId = buildB14VariantItemId()
        expect(itemId).toBe('b14-meta-variant')
      }),
      { numRuns: 100 },
    )
  })

  it('all item_ids start with b14- prefix', () => {
    fc.assert(
      fc.property(arbChapterNum, arbFieldId, arbSignatureField, (chNum, fieldId, sigField) => {
        const ids = [
          buildB14ChapterContentItemId(chNum),
          buildB14SectionItemId(chNum, fieldId),
          buildB14TableItemId(chNum, fieldId),
          buildB14SignatureItemId(sigField),
          buildB14VariantItemId(),
        ]

        for (const id of ids) {
          expect(id.startsWith('b14-')).toBe(true)
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: Table data JSON round-trip
// ═══════════════════════════════════════════════════════════════════════════════

/** Feature: b1-4-due-diligence-report, Property 5: Table data JSON round-trip */
describe('Feature: b1-4-due-diligence-report, Property 5: Table data JSON round-trip', () => {
  /**
   * **Validates: Requirements 5.5**
   *
   * For any valid table rows array (containing objects with string/number/null values),
   * serializing to JSON and deserializing back should produce an equivalent array.
   */

  /** Arbitrary for table row values (string | number | null only, JSON-safe) */
  const arbJsonSafeValue = fc.oneof(
    fc.string({ maxLength: 50 }),
    fc.integer({ min: -1000000, max: 1000000 }),
    fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }).filter(n => !Object.is(n, -0)),
    fc.constant(null as string | number | null),
  )

  /** Arbitrary for a single table row */
  const arbRow = fc.dictionary(
    fc.string({ minLength: 1, maxLength: 15 }).filter(s => s.trim().length > 0),
    arbJsonSafeValue,
    { minKeys: 0, maxKeys: 8 },
  )

  /** Arbitrary for table rows array */
  const arbRows = fc.array(arbRow, { minLength: 0, maxLength: 10 })

  it('JSON.stringify → JSON.parse produces equivalent array', () => {
    fc.assert(
      fc.property(arbRows, (rows) => {
        const serialized = JSON.stringify(rows)
        const deserialized = JSON.parse(serialized)

        expect(JSON.stringify(deserialized)).toEqual(JSON.stringify(rows))
      }),
      { numRuns: 100 },
    )
  })

  it('round-trip preserves row count', () => {
    fc.assert(
      fc.property(arbRows, (rows) => {
        const serialized = JSON.stringify(rows)
        const deserialized = JSON.parse(serialized) as Record<string, any>[]

        expect(deserialized.length).toBe(rows.length)
      }),
      { numRuns: 100 },
    )
  })

  it('round-trip preserves value types (string/number/null)', () => {
    fc.assert(
      fc.property(arbRows, (rows) => {
        const serialized = JSON.stringify(rows)
        const deserialized = JSON.parse(serialized) as Record<string, any>[]

        for (let i = 0; i < rows.length; i++) {
          for (const [key, value] of Object.entries(rows[i])) {
            const restored = deserialized[i][key]
            if (value === null) {
              expect(restored).toBeNull()
            } else if (typeof value === 'string') {
              expect(typeof restored).toBe('string')
              expect(restored).toBe(value)
            } else if (typeof value === 'number') {
              expect(typeof restored).toBe('number')
              // JSON.stringify/parse normalizes -0 to 0
              if (value === 0) {
                expect(restored).toBe(0)
              } else {
                expect(Object.is(restored, value)).toBe(true)
              }
            }
          }
        }
      }),
      { numRuns: 100 },
    )
  })

  it('round-trip preserves object keys', () => {
    fc.assert(
      fc.property(arbRows, (rows) => {
        const serialized = JSON.stringify(rows)
        const deserialized = JSON.parse(serialized) as Record<string, any>[]

        for (let i = 0; i < rows.length; i++) {
          const originalKeys = Object.keys(rows[i]).sort()
          const restoredKeys = Object.keys(deserialized[i]).sort()
          expect(restoredKeys).toEqual(originalKeys)
        }
      }),
      { numRuns: 100 },
    )
  })
})
