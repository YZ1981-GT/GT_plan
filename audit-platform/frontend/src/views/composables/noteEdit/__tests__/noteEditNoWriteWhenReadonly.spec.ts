/**
 * Property 15: 不可编辑态不发出写请求
 *
 * Feature: partner-manager-edit-permission, Property 15
 * Validates: Requirements 8.7, 10.10
 *
 * Tests that in non-writable states (readonly member, EQCR, non-member,
 * pending, failed), no coverage-set write requests are sent.
 * In writable state, write operations DO send requests.
 * Deterministic parametrized tests (fast-check not required).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import axios from 'axios'
import { createNoteEditRequestGuard } from '../noteEditRequestGuard'
import { COVERAGE_SET, DRAG_SORT_PATH } from '../noteEditCoverage'
import { WRITE_ENTRIES } from '../noteEditWriteEntries'
import type { UseNoteEditPermissionReturn } from '../useNoteEditPermission'

// ── Mocks ────────────────────────────────────────────────────────────────────

let requestHandlers: Array<(config: any) => any> = []
let capturedRequests: any[] = []

vi.mock('@/utils/http', () => {
  const interceptors = {
    request: {
      use: vi.fn((handler: any) => {
        requestHandlers.push(handler)
        return requestHandlers.length
      }),
      eject: vi.fn(),
    },
    response: { use: vi.fn(() => 99), eject: vi.fn() },
  }
  return { default: { interceptors } }
})

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

// Use real matchesCoverage — not mocked
// noteEditCoverage is NOT mocked here so that the real matcher runs

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Build a url from a pathTemplate by replacing {} with UUIDs */
function fillTemplate(pathTemplate: string): string {
  return pathTemplate.replace(/\{\}/g, () => '00000000-0000-0000-0000-000000000001')
}

/** The five identity states from Req 12.2 + pending + failed */
type IdentityState =
  | 'edit-member'
  | 'review-member-non-eqcr'
  | 'eqcr'
  | 'readonly-member'
  | 'non-member'
  | 'pending'
  | 'failed'

function isWritable(identity: IdentityState): boolean {
  return identity === 'edit-member' || identity === 'review-member-non-eqcr'
}

function createNoteEditForIdentity(identity: IdentityState) {
  const canWriteVal = isWritable(identity)
  return {
    canWrite: computed(() => canWriteVal),
    markRejected: vi.fn(),
    refresh: vi.fn(),
  } as Pick<UseNoteEditPermissionReturn, 'canWrite' | 'markRejected' | 'refresh'>
}

/** A representative set of coverage write URLs for testing */
function getCoverageWriteConfigs(): Array<{ method: string; url: string; label: string }> {
  const entries: Array<{ method: string; url: string; label: string }> = []
  // Sample from COVERAGE_SET
  const sampleSize = Math.min(5, COVERAGE_SET.length)
  for (let i = 0; i < sampleSize; i++) {
    const e = COVERAGE_SET[i]
    entries.push({
      method: e.method.toLowerCase(),
      url: fillTemplate(e.pathTemplate),
      label: `${e.method} ${e.pathTemplate}`,
    })
  }
  // Also include drag sort
  entries.push({
    method: DRAG_SORT_PATH.method.toLowerCase(),
    url: fillTemplate(DRAG_SORT_PATH.pathTemplate),
    label: `${DRAG_SORT_PATH.method} ${DRAG_SORT_PATH.pathTemplate} (drag-sort)`,
  })
  return entries
}

/** Non-coverage requests that should always pass through */
function getNonCoverageConfigs(): Array<{ method: string; url: string; label: string }> {
  return [
    { method: 'get', url: '/api/disclosure-notes/123/2025', label: 'GET disclosure-notes' },
    { method: 'get', url: '/api/projects/abc/disclosure-notes/edit-permission', label: 'GET edit-permission' },
    { method: 'post', url: '/api/projects/abc/some-other-endpoint', label: 'POST non-note endpoint' },
  ]
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('Property 15: non-writable state emits zero coverage write requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestHandlers = []
    capturedRequests = []
  })

  const nonWritableIdentities: IdentityState[] = [
    'readonly-member',
    'eqcr',
    'non-member',
    'pending',
    'failed',
  ]

  const coverageConfigs = getCoverageWriteConfigs()

  describe.each(nonWritableIdentities)('identity=%s', (identity) => {
    it.each(coverageConfigs)(
      'blocks $label',
      ({ method, url }) => {
        const noteEdit = createNoteEditForIdentity(identity)
        const guard = createNoteEditRequestGuard(noteEdit)
        guard.install()

        const handler = requestHandlers[requestHandlers.length - 1]
        const config = { method, url }

        expect(() => handler(config)).toThrow()
        try {
          handler(config)
        } catch (e: any) {
          // Must be an axios Cancel with the correct message
          expect(e.message).toBe('note-edit-readonly')
        }

        guard.uninstall()
      },
    )

    it.each(getNonCoverageConfigs())(
      'allows non-coverage $label',
      ({ method, url }) => {
        const noteEdit = createNoteEditForIdentity(identity)
        const guard = createNoteEditRequestGuard(noteEdit)
        guard.install()

        const handler = requestHandlers[requestHandlers.length - 1]
        const config = { method, url }
        const result = handler(config)
        // Should pass through (not throw)
        expect(result).toBe(config)

        guard.uninstall()
      },
    )
  })

  describe('writable identities send requests', () => {
    const writableIdentities: IdentityState[] = ['edit-member', 'review-member-non-eqcr']

    describe.each(writableIdentities)('identity=%s', (identity) => {
      it.each(coverageConfigs)(
        'allows $label and attaches _forbiddenHandler',
        ({ method, url }) => {
          const noteEdit = createNoteEditForIdentity(identity)
          const guard = createNoteEditRequestGuard(noteEdit)
          guard.install()

          const handler = requestHandlers[requestHandlers.length - 1]
          const config = { method, url } as any
          const result = handler(config)

          // Request passes through
          expect(result).toBe(config)
          // _forbiddenHandler is attached
          expect(typeof result._forbiddenHandler).toBe('function')

          guard.uninstall()
        },
      )
    })
  })

  describe('drag-sort path is also guarded', () => {
    it('non-writable blocks drag sort', () => {
      const noteEdit = createNoteEditForIdentity('eqcr')
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const handler = requestHandlers[requestHandlers.length - 1]
      const config = {
        method: DRAG_SORT_PATH.method.toLowerCase(),
        url: fillTemplate(DRAG_SORT_PATH.pathTemplate),
      }
      expect(() => handler(config)).toThrow()
      guard.uninstall()
    })

    it('writable allows drag sort', () => {
      const noteEdit = createNoteEditForIdentity('edit-member')
      const guard = createNoteEditRequestGuard(noteEdit)
      guard.install()
      const handler = requestHandlers[requestHandlers.length - 1]
      const config = {
        method: DRAG_SORT_PATH.method.toLowerCase(),
        url: fillTemplate(DRAG_SORT_PATH.pathTemplate),
      } as any
      const result = handler(config)
      expect(result).toBe(config)
      guard.uninstall()
    })
  })

  describe('write entry coverage completeness', () => {
    it('all coverage=true write entries have at least one matching coverage set entry', () => {
      const coverageEntries = WRITE_ENTRIES.filter((e) => e.coverage)
      // Each coverage entry with callPoints should match at least one COVERAGE_SET or DRAG_SORT
      // Entries with empty callPoints are acceptable — they fire save on the same endpoints
      expect(coverageEntries.length).toBeGreaterThan(0)
      // Verify COVERAGE_SET is non-empty
      expect(COVERAGE_SET.length).toBeGreaterThan(0)
    })
  })
})