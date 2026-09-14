import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

/**
 * B60 Frontend Property-Based Tests
 * 
 * Pure function extraction for property testing — no component mounting needed.
 * Tests validate correctness properties from the design document.
 */

// ─── Pure functions under test ───────────────────────────────────────────────

/**
 * Property 2: Tab visibility derived from wpIdMap + applicability
 * **Validates: Requirements 2.1, 2.2, 3.2**
 */
function computeTabVisibility(
  tabKind: string,
  wpCode: string,
  wpIdMap: Record<string, string>,
  applicabilityMap: Record<string, boolean>
): boolean {
  // B60 main tab (chapter-editor) is always visible
  if (tabKind === 'chapter-editor') return true
  // If not applicable, hidden
  const applicable = applicabilityMap[wpCode] ?? true
  if (!applicable) return false
  // If applicable but no wpIdMap entry, hidden
  return !!wpIdMap[wpCode]
}

/**
 * Property 5: Completion indicator color derived from remark + required
 * **Validates: Requirements 5.2**
 */
function getStatusColor(remark: string, required: boolean): 'green' | 'orange' | 'gray' {
  if (remark.trim().length > 0) return 'green'
  if (required) return 'orange'
  return 'gray'
}

/**
 * Property 8: Chapter metadata drives UI element rendering
 * **Validates: Requirements 5.5, 8.1**
 */
function shouldRenderHint(hint: string): boolean {
  return hint.length > 0
}

function shouldRenderPullButton(dataSource: { label: string; wp_code: string } | null | undefined): boolean {
  return dataSource !== null && dataSource !== undefined
}

/**
 * Property 9: Data pull append semantics
 * **Validates: Requirements 8.3**
 */
function applyPullContent(existing: string, pulled: string): string {
  return existing.trim() ? `${existing}\n\n${pulled}` : pulled
}

// ─── Arbitraries ─────────────────────────────────────────────────────────────

const B60_SUB_WP_CODES = ['B60-1', 'B60-2-1', 'B60-2-2', 'B60-2-3', 'B60-3', 'B60A', 'B60B', 'B60C', 'B60D'] as const

const wpCodeArb = fc.constantFrom(...B60_SUB_WP_CODES)

const wpIdArb = fc.uuid()

/** Generate a random wpIdMap (subset of B60 sub-wp-codes → wp_id) */
const wpIdMapArb = fc.subarray([...B60_SUB_WP_CODES]).chain(codes =>
  fc.tuple(...codes.map(() => wpIdArb)).map(ids => {
    const map: Record<string, string> = {}
    codes.forEach((code, i) => { map[code] = ids[i] })
    return map
  })
)

/** Generate a random applicability map (subset of B60 codes → boolean) */
const applicabilityMapArb = fc.subarray([...B60_SUB_WP_CODES]).chain(codes =>
  fc.tuple(...codes.map(() => fc.boolean())).map(bools => {
    const map: Record<string, boolean> = {}
    codes.forEach((code, i) => { map[code] = bools[i] })
    return map
  })
)

const tabKindArb = fc.constantFrom('chapter-editor', 'navigate-sheet', 'docx-inline')

const remarkArb = fc.oneof(
  fc.constant(''),
  fc.constant('   '),
  fc.string({ minLength: 1, maxLength: 200 })
)

const dataSourceArb = fc.oneof(
  fc.constant(null),
  fc.constant(undefined),
  fc.record({
    label: fc.string({ minLength: 1, maxLength: 50 }),
    wp_code: fc.string({ minLength: 2, maxLength: 10 })
  })
)

const contentArb = fc.oneof(
  fc.constant(''),
  fc.constant('   '),
  fc.string({ minLength: 1, maxLength: 500 })
)

// ─── Property Tests ──────────────────────────────────────────────────────────

describe('B60 Frontend Properties', () => {
  describe('Property 2: Tab 可见性推导 (Tab visibility derived from wpIdMap + applicability)', () => {
    it('Rule 1: chapter-editor tab is ALWAYS visible regardless of wpIdMap/applicability', () => {
      /**
       * **Validates: Requirements 2.1, 2.2, 3.2**
       */
      fc.assert(fc.property(
        wpCodeArb,
        wpIdMapArb,
        applicabilityMapArb,
        (wpCode, wpIdMap, applicabilityMap) => {
          const result = computeTabVisibility('chapter-editor', wpCode, wpIdMap, applicabilityMap)
          expect(result).toBe(true)
        }
      ), { numRuns: 20 })
    })

    it('Rule 2: applicable=false → tab is hidden', () => {
      /**
       * **Validates: Requirements 2.1, 2.2, 3.2**
       */
      fc.assert(fc.property(
        fc.constantFrom('navigate-sheet', 'docx-inline'),
        wpCodeArb,
        wpIdMapArb,
        (tabKind, wpCode, wpIdMap) => {
          const applicabilityMap: Record<string, boolean> = { [wpCode]: false }
          const result = computeTabVisibility(tabKind, wpCode, wpIdMap, applicabilityMap)
          expect(result).toBe(false)
        }
      ), { numRuns: 20 })
    })

    it('Rule 3: applicable=true but no wpIdMap entry → tab is hidden', () => {
      /**
       * **Validates: Requirements 2.1, 2.2, 3.2**
       */
      fc.assert(fc.property(
        fc.constantFrom('navigate-sheet', 'docx-inline'),
        wpCodeArb,
        (tabKind, wpCode) => {
          const wpIdMap: Record<string, string> = {} // no entry for wpCode
          const applicabilityMap: Record<string, boolean> = { [wpCode]: true }
          const result = computeTabVisibility(tabKind, wpCode, wpIdMap, applicabilityMap)
          expect(result).toBe(false)
        }
      ), { numRuns: 20 })
    })

    it('Rule 4: applicable=true AND wpIdMap has entry → tab is visible', () => {
      /**
       * **Validates: Requirements 2.1, 2.2, 3.2**
       */
      fc.assert(fc.property(
        fc.constantFrom('navigate-sheet', 'docx-inline'),
        wpCodeArb,
        wpIdArb,
        (tabKind, wpCode, wpId) => {
          const wpIdMap: Record<string, string> = { [wpCode]: wpId }
          const applicabilityMap: Record<string, boolean> = { [wpCode]: true }
          const result = computeTabVisibility(tabKind, wpCode, wpIdMap, applicabilityMap)
          expect(result).toBe(true)
        }
      ), { numRuns: 20 })
    })
  })

  describe('Property 5: 完成指示器颜色 (Completion indicator color)', () => {
    it('remark non-empty → green', () => {
      /**
       * **Validates: Requirements 5.2**
       */
      fc.assert(fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        fc.boolean(),
        (remark, required) => {
          // Ensure remark has non-whitespace content
          fc.pre(remark.trim().length > 0)
          expect(getStatusColor(remark, required)).toBe('green')
        }
      ), { numRuns: 20 })
    })

    it('remark empty + required=true → orange', () => {
      /**
       * **Validates: Requirements 5.2**
       */
      fc.assert(fc.property(
        fc.constantFrom('', '   ', '\t', '\n', '  \n  '),
        (_emptyRemark) => {
          expect(getStatusColor(_emptyRemark, true)).toBe('orange')
        }
      ), { numRuns: 20 })
    })

    it('remark empty + required=false → gray', () => {
      /**
       * **Validates: Requirements 5.2**
       */
      fc.assert(fc.property(
        fc.constantFrom('', '   ', '\t', '\n', '  \n  '),
        (_emptyRemark) => {
          expect(getStatusColor(_emptyRemark, false)).toBe('gray')
        }
      ), { numRuns: 20 })
    })

    it('exhaustive: all combinations satisfy exactly one color rule', () => {
      /**
       * **Validates: Requirements 5.2**
       */
      fc.assert(fc.property(
        remarkArb,
        fc.boolean(),
        (remark, required) => {
          const color = getStatusColor(remark, required)
          const hasContent = remark.trim().length > 0
          if (hasContent) {
            expect(color).toBe('green')
          } else if (required) {
            expect(color).toBe('orange')
          } else {
            expect(color).toBe('gray')
          }
        }
      ), { numRuns: 20 })
    })
  })

  describe('Property 8: 章节元数据驱动 UI (Chapter metadata drives UI rendering)', () => {
    it('hint non-empty → render hint block; hint empty → no hint block', () => {
      /**
       * **Validates: Requirements 5.5, 8.1**
       */
      fc.assert(fc.property(
        fc.string({ minLength: 0, maxLength: 200 }),
        (hint) => {
          const shouldRender = shouldRenderHint(hint)
          if (hint.length > 0) {
            expect(shouldRender).toBe(true)
          } else {
            expect(shouldRender).toBe(false)
          }
        }
      ), { numRuns: 20 })
    })

    it('data_source non-null → render pull button; data_source null → no pull button', () => {
      /**
       * **Validates: Requirements 5.5, 8.1**
       */
      fc.assert(fc.property(
        dataSourceArb,
        (dataSource) => {
          const shouldRender = shouldRenderPullButton(dataSource)
          if (dataSource !== null && dataSource !== undefined) {
            expect(shouldRender).toBe(true)
          } else {
            expect(shouldRender).toBe(false)
          }
        }
      ), { numRuns: 20 })
    })
  })

  describe('Property 9: 数据拉取追加语义 (Data pull append semantics)', () => {
    it('existing empty → set to pulled content', () => {
      /**
       * **Validates: Requirements 8.3**
       */
      fc.assert(fc.property(
        fc.constantFrom('', '   ', '\t'),
        fc.string({ minLength: 1, maxLength: 200 }),
        (existing, pulled) => {
          const result = applyPullContent(existing, pulled)
          expect(result).toBe(pulled)
        }
      ), { numRuns: 20 })
    })

    it('existing non-empty → existing + newline*2 + pulled', () => {
      /**
       * **Validates: Requirements 8.3**
       */
      fc.assert(fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        fc.string({ minLength: 1, maxLength: 200 }),
        (existing, pulled) => {
          // Ensure existing has actual content (non-whitespace)
          fc.pre(existing.trim().length > 0)
          const result = applyPullContent(existing, pulled)
          expect(result).toBe(`${existing}\n\n${pulled}`)
        }
      ), { numRuns: 20 })
    })

    it('result always contains pulled content', () => {
      /**
       * **Validates: Requirements 8.3**
       */
      fc.assert(fc.property(
        contentArb,
        fc.string({ minLength: 1, maxLength: 200 }),
        (existing, pulled) => {
          const result = applyPullContent(existing, pulled)
          expect(result).toContain(pulled)
        }
      ), { numRuns: 20 })
    })

    it('when existing non-empty, result preserves original content at start', () => {
      /**
       * **Validates: Requirements 8.3**
       */
      fc.assert(fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        fc.string({ minLength: 1, maxLength: 200 }),
        (existing, pulled) => {
          fc.pre(existing.trim().length > 0)
          const result = applyPullContent(existing, pulled)
          expect(result.startsWith(existing)).toBe(true)
        }
      ), { numRuns: 20 })
    })
  })
})
