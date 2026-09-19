/**
 * Trivial import test for hardening generators.
 *
 * Feature: advanced-query-disclosure-integration-hardening, Property P1–P12
 *
 * Verifies that all generators are importable and produce valid samples.
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  arbDraftContext,
  arbDisclosureCell,
  arbOperationSequence,
  arbOperation,
  arbProjectId,
  arbYear,
  arbSection,
} from './hardening-generators'

describe('hardening-generators import smoke', () => {
  it('arbDraftContext produces valid context objects', () => {
    fc.assert(
      fc.property(arbDraftContext, (ctx) => {
        expect(ctx.project_id).toBeTruthy()
        expect(ctx.year).toBeGreaterThanOrEqual(2020)
        expect(ctx.section).toBeTruthy()
      }),
      { numRuns: 5 },
    )
  })

  it('arbDisclosureCell produces valid cell objects', () => {
    fc.assert(
      fc.property(arbDisclosureCell, (cell) => {
        expect(typeof cell.manual).toBe('boolean')
        expect(Array.isArray(cell.provenance)).toBe(true)
        expect(Array.isArray(cell.trace)).toBe(true)
      }),
      { numRuns: 5 },
    )
  })

  it('arbOperationSequence produces non-empty arrays', () => {
    fc.assert(
      fc.property(arbOperationSequence, (ops) => {
        expect(ops.length).toBeGreaterThanOrEqual(1)
        for (const op of ops) {
          expect(['edit', 'save', 'refresh', 'pageChange', 'templateExec', 'reopen']).toContain(op.type)
        }
      }),
      { numRuns: 5 },
    )
  })

  it('individual arbitraries produce expected shapes', () => {
    fc.assert(fc.property(arbProjectId, (id) => typeof id === 'string' && id.startsWith('proj-')), { numRuns: 5 })
    fc.assert(fc.property(arbYear, (y) => y >= 2020 && y <= 2030), { numRuns: 5 })
    fc.assert(fc.property(arbSection, (s) => typeof s === 'string' && s.length > 0), { numRuns: 5 })
    fc.assert(fc.property(arbOperation, (op) => 'type' in op), { numRuns: 5 })
  })
})
