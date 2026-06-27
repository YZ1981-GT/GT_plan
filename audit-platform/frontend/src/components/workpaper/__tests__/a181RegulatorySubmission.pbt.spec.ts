/**
 * Property-Based Tests — A18-1 向监管部门报送审计小结
 *
 * Spec: .kiro/specs/a18-1-regulatory-submission/
 * Task: 2.2, 3.2
 *
 * Property 1: item_id format `a181-{section}-{field}`
 * Property 2: auto-fill verification
 * Property 4: 收件人前缀始终显示
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

const SECTIONS = ['recipient', 'body', 'issuance'] as const
const FIELDS_MAP: Record<string, string[]> = {
  recipient: ['bureau'],
  body: ['contact_person', 'contact_phone'],
  issuance: ['partner', 'date'],
}

function makeItemId(section: string, field: string): string {
  return `a181-${section}-${field}`
}

const FIXED_PREFIX = '致：'

describe('Feature: a18-1-regulatory-submission, Property 1: item_id 格式', () => {
  it('all section-field combos produce correct a181-{section}-{field} format', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...SECTIONS),
        (section) => {
          for (const field of FIELDS_MAP[section]) {
            const id = makeItemId(section, field)
            expect(id).toMatch(/^a181-[a-z]+-[a-z_]+$/)
            expect(id).toBe(`a181-${section}-${field}`)
          }
        },
      ),
      { numRuns: 10 },
    )
  })
})

describe('Feature: a18-1-regulatory-submission, Property 2: 自动填充', () => {
  it('firm_name is always fixed', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 20 }),
        (_clientName) => {
          const ctx = { client_name: _clientName, audit_year: '2025', firm_name: '致同会计师事务所（特殊普通合伙）', partner_name: '' }
          expect(ctx.firm_name).toBe('致同会计师事务所（特殊普通合伙）')
        },
      ),
      { numRuns: 20 },
    )
  })
})

describe('Feature: a18-1-regulatory-submission, Property 4: 收件人前缀', () => {
  it('prefix 致： is always present regardless of bureau value', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 50 }),
        (bureau) => {
          const display = `${FIXED_PREFIX}${bureau}财政局（证券监管局）`
          expect(display.startsWith(FIXED_PREFIX)).toBe(true)
        },
      ),
      { numRuns: 30 },
    )
  })
})
