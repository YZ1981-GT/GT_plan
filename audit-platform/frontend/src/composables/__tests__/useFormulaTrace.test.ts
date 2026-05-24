/**
 * Tests for FormulaTracePopover formula classification
 *
 * Feature: advanced-query-enhancements-p1p2
 * - Property 23: 公式分类
 *
 * **Validates: Requirements 12.2, 12.3**
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  classifyFormula,
  parseCrossSheetRefs,
  parseLocalRefs,
} from '../../components/custom-query/FormulaTracePopover.vue'

// ---------------------------------------------------------------------------
// Property 23: Formula classification
// Feature: advanced-query-enhancements-p1p2, Property 23: Formula classification
// ---------------------------------------------------------------------------

describe('Property 23: Formula classification', () => {
  it('correctly classifies cross-sheet vs local vs parse-error', () => {
    // Generate formulas of different types
    const crossSheetFormula = fc.oneof(
      // =SheetName!A1
      fc.tuple(
        fc.stringMatching(/^[A-Z][a-zA-Z\u4e00-\u9fff]{0,10}$/),
        fc.stringMatching(/^[A-Z]{1,2}\d{1,4}$/)
      ).map(([sheet, cell]) => `=${sheet}!${cell}`),
      // ='Sheet Name'!A1
      fc.tuple(
        fc.string({ minLength: 1, maxLength: 10 }).filter(s => !s.includes("'")),
        fc.stringMatching(/^[A-Z]{1,2}\d{1,4}$/)
      ).map(([sheet, cell]) => `='${sheet}'!${cell}`)
    )

    const localFormula = fc.oneof(
      // =A1+B2
      fc.tuple(
        fc.stringMatching(/^[A-Z]\d{1,3}$/),
        fc.stringMatching(/^[A-Z]\d{1,3}$/)
      ).map(([a, b]) => `=${a}+${b}`),
      // =SUM(A1:A10)
      fc.stringMatching(/^[A-Z]\d{1,3}$/).map(c => `=SUM(${c}:${c})`)
    )

    const invalidFormula = fc.oneof(
      fc.constant(''),
      fc.constant('hello'),
      fc.constant('123'),
      fc.string({ minLength: 1, maxLength: 10 }).filter(s => !s.startsWith('=') && !s.startsWith('+'))
    )

    // Test cross-sheet formulas
    fc.assert(
      fc.property(crossSheetFormula, (formula) => {
        const result = classifyFormula(formula)
        expect(result).toBe('cross-sheet')
      }),
      { numRuns: 20 }
    )

    // Test local formulas
    fc.assert(
      fc.property(localFormula, (formula) => {
        const result = classifyFormula(formula)
        expect(result).toBe('local')
      }),
      { numRuns: 20 }
    )

    // Test invalid formulas
    fc.assert(
      fc.property(invalidFormula, (formula) => {
        const result = classifyFormula(formula)
        expect(result).toBe('parse-error')
      }),
      { numRuns: 20 }
    )
  })

  it('cross-sheet: detects =Sheet!Cell pattern', () => {
    expect(classifyFormula("=底稿目录!A2")).toBe('cross-sheet')
    expect(classifyFormula("='Sheet Name'!B7")).toBe('cross-sheet')
    expect(classifyFormula("=Sheet1!A1+Sheet2!B2")).toBe('cross-sheet')
  })

  it('local: detects pure local references', () => {
    expect(classifyFormula("=A1+B1")).toBe('local')
    expect(classifyFormula("=SUM(A1:A10)")).toBe('local')
    expect(classifyFormula("=C5*2")).toBe('local')
  })

  it('parse-error: non-formula strings', () => {
    expect(classifyFormula("")).toBe('parse-error')
    expect(classifyFormula("hello")).toBe('parse-error')
    expect(classifyFormula("123")).toBe('parse-error')
  })

  it('local: pure computation formulas (=1+2)', () => {
    expect(classifyFormula("=1+2")).toBe('local')
    expect(classifyFormula("=100")).toBe('local')
  })
})

// ---------------------------------------------------------------------------
// parseCrossSheetRefs tests
// ---------------------------------------------------------------------------

describe('parseCrossSheetRefs', () => {
  it('extracts sheet and cell from cross-sheet references', () => {
    const refs = parseCrossSheetRefs("=底稿目录!A2")
    expect(refs).toHaveLength(1)
    expect(refs[0]).toEqual({ sheet: '底稿目录', cell: 'A2' })
  })

  it('extracts quoted sheet names', () => {
    const refs = parseCrossSheetRefs("='My Sheet'!B7")
    expect(refs).toHaveLength(1)
    expect(refs[0]).toEqual({ sheet: 'My Sheet', cell: 'B7' })
  })

  it('extracts multiple cross-sheet references', () => {
    const refs = parseCrossSheetRefs("=Sheet1!A1+Sheet2!B2")
    expect(refs).toHaveLength(2)
    expect(refs[0]).toEqual({ sheet: 'Sheet1', cell: 'A1' })
    expect(refs[1]).toEqual({ sheet: 'Sheet2', cell: 'B2' })
  })

  it('returns empty for local-only formulas', () => {
    const refs = parseCrossSheetRefs("=A1+B2")
    expect(refs).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// parseLocalRefs tests
// ---------------------------------------------------------------------------

describe('parseLocalRefs', () => {
  it('extracts local cell references', () => {
    const refs = parseLocalRefs("=A1+B2*C3")
    expect(refs).toContain('A1')
    expect(refs).toContain('B2')
    expect(refs).toContain('C3')
  })

  it('excludes cross-sheet references from local refs', () => {
    const refs = parseLocalRefs("=Sheet1!A1+B2")
    // A1 is part of Sheet1!A1, should not appear as local
    expect(refs).not.toContain('A1')
    expect(refs).toContain('B2')
  })

  it('deduplicates references', () => {
    const refs = parseLocalRefs("=A1+A1+A1")
    expect(refs.filter(r => r === 'A1')).toHaveLength(1)
  })
})
