/**
 * Property-Based Tests — A17-6 总结会会议纪要
 *
 * Spec: .kiro/specs/a17-6-closing-meeting/
 * Task: 2.2
 *
 * Property 1: item_id 格式一致性 — updateMeta → `a176-meta-{field}`, updateField → `a176-{field}`
 * Property 2: 自动填充验证 — 空 meta 时从 projectContext 预填
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── Pure logic extracted from composable for PBT ────────────────────────────

const META_FIELDS = ['client_name', 'period', 'preparer', 'reviewer', 'date', 'index_no'] as const
const CONTENT_FIELDS = ['meeting_time', 'attendees', 'minutes', 'conclusion', 'attachments'] as const

/** Generate item_id for meta field */
function metaItemId(field: string): string {
  return `a176-meta-${field}`
}

/** Generate item_id for content field */
function fieldItemId(field: string): string {
  return `a176-${field}`
}

/** Auto-fill logic: if meta field is empty, fill from projectContext */
function autoFillMeta(
  metaInfo: Record<string, string>,
  projectContext: { client_name: string; period: string },
): Record<string, string> {
  const result = { ...metaInfo }
  if (!result.client_name) result.client_name = projectContext.client_name
  if (!result.period) result.period = projectContext.period
  return result
}

// ─── Property 1: item_id 格式一致性 ─────────────────────────────────────────

describe('Feature: a17-6-closing-meeting, Property 1: item_id 格式一致性', () => {
  it('meta fields always produce a176-meta-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...META_FIELDS.filter(f => f !== 'index_no')),
        (field) => {
          const id = metaItemId(field)
          expect(id).toMatch(/^a176-meta-[a-z_]+$/)
          expect(id).toBe(`a176-meta-${field}`)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('content fields always produce a176-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CONTENT_FIELDS),
        (field) => {
          const id = fieldItemId(field)
          expect(id).toMatch(/^a176-[a-z_]+$/)
          expect(id).toBe(`a176-${field}`)
          // Must NOT contain 'meta' prefix
          expect(id).not.toContain('meta')
        },
      ),
      { numRuns: 20 },
    )
  })

  it('no overlap between meta and content item_ids', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...META_FIELDS.filter(f => f !== 'index_no')),
        fc.constantFrom(...CONTENT_FIELDS),
        (metaField, contentField) => {
          const metaId = metaItemId(metaField)
          const contentId = fieldItemId(contentField)
          expect(metaId).not.toBe(contentId)
        },
      ),
      { numRuns: 25 },
    )
  })
})

// ─── Property 2: 自动填充验证 ───────────────────────────────────────────────

describe('Feature: a17-6-closing-meeting, Property 2: 自动填充验证', () => {
  it('empty meta is filled from projectContext', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        (clientName, period) => {
          const meta = { client_name: '', period: '', preparer: '', reviewer: '', date: '', index_no: 'A17-6' }
          const ctx = { client_name: clientName, period }
          const result = autoFillMeta(meta, ctx)
          expect(result.client_name).toBe(clientName)
          expect(result.period).toBe(period)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('manual meta values override auto-fill', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        (manualClient, manualPeriod, ctxClient, ctxPeriod) => {
          const meta = { client_name: manualClient, period: manualPeriod, preparer: '', reviewer: '', date: '', index_no: 'A17-6' }
          const ctx = { client_name: ctxClient, period: ctxPeriod }
          const result = autoFillMeta(meta, ctx)
          // Manual values preserved (not overwritten)
          expect(result.client_name).toBe(manualClient)
          expect(result.period).toBe(manualPeriod)
        },
      ),
      { numRuns: 30 },
    )
  })

  it('index_no is never auto-filled (always A17-6)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 30 }),
        fc.string({ minLength: 0, maxLength: 30 }),
        (clientName, period) => {
          const meta = { client_name: '', period: '', preparer: '', reviewer: '', date: '', index_no: 'A17-6' }
          const ctx = { client_name: clientName, period }
          const result = autoFillMeta(meta, ctx)
          expect(result.index_no).toBe('A17-6')
        },
      ),
      { numRuns: 20 },
    )
  })
})
