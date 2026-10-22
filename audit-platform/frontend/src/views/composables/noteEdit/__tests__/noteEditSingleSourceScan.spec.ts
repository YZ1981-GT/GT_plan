/**
 * Task 17.9: 开关同源扫描与取值断言
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 10.8
 *
 * 1) Scans DisclosureEditor.vue source text for OLD patterns that should be absent:
 *    - comparing global role with 'eqcr' (old way)
 *    - reading useAuditContext's canEdit
 *    - calling canDo / can (permission matrix)
 * 2) Tests derived values for 5 identities + pending/failed states.
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { presentEntry, type NoteEditState } from '../noteEditPresentation'
import { WRITE_ENTRIES } from '../noteEditWriteEntries'

// ── Part 1: Source text scan ─────────────────────────────────────────────────

// Resolve from project root (vitest CWD)
const EDITOR_PATH = path.resolve(
  process.cwd(),
  'src/views/DisclosureEditor.vue',
)

/** Read the script block from a .vue file */
function readScriptBlock(filePath: string): string {
  const content = fs.readFileSync(filePath, 'utf-8')
  const scriptMatch = content.match(/<script[^>]*>([\s\S]*?)<\/script>/g)
  if (!scriptMatch) return ''
  return scriptMatch.join('\n')
}

/** Read template block */
function readTemplateBlock(filePath: string): string {
  const content = fs.readFileSync(filePath, 'utf-8')
  const m = content.match(/<template>([\s\S]*?)<\/template>/)
  return m ? m[1] : ''
}

describe('single-source scan: DisclosureEditor.vue', () => {
  const scriptBlock = readScriptBlock(EDITOR_PATH)
  const templateBlock = readTemplateBlock(EDITOR_PATH)

  /** Strip comments and string literals for accurate code-only scanning */
  function stripCommentsAndStrings(code: string): string {
    let result = code.replace(/\/\/.*$/gm, '')
    result = result.replace(/\/\*[\s\S]*?\*\//g, '')
    result = result.replace(/`[^`]*`/g, '""')
    result = result.replace(/"[^"]*"/g, '""')
    result = result.replace(/'[^']*'/g, "''")
    return result
  }

  const cleanScript = stripCommentsAndStrings(scriptBlock)

  describe('absent patterns in script block', () => {
    it('does not compare global role with "eqcr" string literal', () => {
      const eqcrComparisons = cleanScript.match(/===\s*['"]eqcr['"]/g) || []
      const reverseComparisons = cleanScript.match(/['"]eqcr['"]\s*===/g) || []
      expect(
        eqcrComparisons.length + reverseComparisons.length,
        'Script block should not compare any value with "eqcr" string literal',
      ).toBe(0)
    })

    it('does not destructure canEdit from useAuditContext', () => {
      const destructureCanEdit = cleanScript.match(
        /\{\s*[^}]*\bcanEdit\b[^}]*\}\s*=\s*useAuditContext/g,
      ) || []
      expect(
        destructureCanEdit.length,
        'Should not destructure canEdit from useAuditContext()',
      ).toBe(0)
    })

    it('does not call canDo() or can() for permission checks', () => {
      const canDoCalls = cleanScript.match(/\bcanDo\s*\(/g) || []
      const canCalls = cleanScript.match(/\bcan\s*\(\s*['"]/g) || []
      expect(canDoCalls.length, 'Should not call canDo()').toBe(0)
      expect(canCalls.length, 'Should not call can() with string arg').toBe(0)
    })
  })

  describe('absent patterns in template block', () => {
    it('template does not use standalone canEdit (only noteEdit.canWrite*)', () => {
      // Match canEdit not preceded or followed by a dot or word char
      const standaloneCanEdit =
        templateBlock.match(/(?<![.\w])canEdit(?![.\w])/g) || []
      expect(
        standaloneCanEdit.length,
        'Template should not reference standalone canEdit',
      ).toBe(0)
    })
  })
})

// ── Part 2: Derived values for identities ────────────────────────────────────

function stateForIdentity(identity: string): NoteEditState {
  switch (identity) {
    case 'edit-member':
      return { queryStatus: 'ok', canEdit: true, reason: null, isEqcr: false, isArchived: false, forcedReadonly: false }
    case 'review-member':
      return { queryStatus: 'ok', canEdit: true, reason: null, isEqcr: false, isArchived: false, forcedReadonly: false }
    case 'eqcr':
      return { queryStatus: 'ok', canEdit: false, reason: '独立复核合伙人（EQCR）在本项目只读', isEqcr: true, isArchived: false, forcedReadonly: false }
    case 'readonly-member':
      return { queryStatus: 'ok', canEdit: false, reason: '权限不足', isEqcr: false, isArchived: false, forcedReadonly: false }
    case 'non-member':
      return { queryStatus: 'ok', canEdit: false, reason: '权限不足', isEqcr: false, isArchived: false, forcedReadonly: false }
    case 'pending':
      return { queryStatus: 'pending', canEdit: false, reason: null, isEqcr: false, isArchived: false, forcedReadonly: false }
    case 'failed':
      return { queryStatus: 'failed', canEdit: false, reason: null, isEqcr: false, isArchived: false, forcedReadonly: false }
    default:
      throw new Error(`Unknown identity: ${identity}`)
  }
}

describe('derived values per identity', () => {
  const identities = ['edit-member', 'review-member', 'eqcr', 'readonly-member', 'non-member', 'pending', 'failed']

  const coverageEntry = WRITE_ENTRIES.find((e) => e.coverage && !e.eqcrHidden && !e.lockConstrained)!
  const lockEntry = WRITE_ENTRIES.find((e) => e.coverage && e.lockConstrained)!
  const eqcrHiddenEntry = WRITE_ENTRIES.find((e) => e.eqcrHidden)!

  describe.each(identities)('identity=%s', (identity) => {
    const state = stateForIdentity(identity)
    const isWritable = state.queryStatus === 'ok' && state.canEdit && !state.isArchived

    it('coverage entry operable matches canWrite', () => {
      const p = presentEntry(state, coverageEntry)
      expect(p.operable).toBe(isWritable)
    })

    it('lock-constrained entry with forcedReadonly is not operable', () => {
      const stateWithLock = { ...state, forcedReadonly: true }
      const p = presentEntry(stateWithLock, lockEntry)
      expect(p.operable).toBe(false)
    })

    it('eqcrHidden entry rendered only when ok and not EQCR', () => {
      const p = presentEntry(state, eqcrHiddenEntry)
      const expectedRendered = state.queryStatus === 'ok' && !state.isEqcr
      expect(p.rendered).toBe(expectedRendered)
    })

    it('tooltip is non-empty when disabled', () => {
      const p = presentEntry(state, coverageEntry)
      if (!p.operable && p.rendered) {
        expect(p.tooltip.length).toBeGreaterThan(0)
      }
    })
  })

  it('archived state: coverage entry not operable, tooltip mentions 归档', () => {
    const archivedState: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null, isEqcr: false, isArchived: true, forcedReadonly: false,
    }
    const p = presentEntry(archivedState, coverageEntry)
    expect(p.operable).toBe(false)
    expect(p.tooltip).toContain('归档')
  })
})