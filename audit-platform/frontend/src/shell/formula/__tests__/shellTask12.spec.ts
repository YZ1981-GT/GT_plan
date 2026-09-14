/**
 * Formula-toolbar Task 12 — responsive / a11y / errors / cleanup.
 */

import { describe, expect, it, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  SHELL_VIEWPORTS,
  assertShellLayoutNonOverlap,
  classifyShellViewport,
  resolveShellLayoutTokens,
} from '@/shell/formula/shellResponsiveLayout'
import {
  SHELL_A11Y_NAMES,
  acquireShellScrollLock,
  activeShellFocusTrapIds,
  assertChineseAccessibleName,
  beginShellFocusSession,
  endShellFocusSession,
  handleShellEscapeKey,
  releaseShellScrollLock,
  resetShellFocusSessionsForTests,
  resetShellScrollLockForTests,
} from '@/shell/formula/shellA11y'
import {
  assertNotBroadCatchSuccess,
  containsSensitiveShellPayload,
  createShellStructuredError,
  toShellSafeLog,
} from '@/shell/formula/shellStructuredError'
import { parseCapabilitySnapshotPayload } from '@/shell/formula/fetchCapabilitySnapshot'
import {
  scanAuditWarningThenCommit,
  scanBareAiMount,
  scanFixedReviewRailSource,
  scanHardcodedCapabilityAvailability,
} from '@/shell/formula/legacyCleanupScanners'

describe('Task 12: responsive shell layout', () => {
  it('uses one algorithm for 1280/1440/1920 and 200% zoom', () => {
    expect(SHELL_VIEWPORTS).toEqual([1280, 1440, 1920])
    expect(classifyShellViewport(1280)).toBe('compact')
    expect(classifyShellViewport(1440)).toBe('standard')
    expect(classifyShellViewport(1920)).toBe('wide')

    const at200 = resolveShellLayoutTokens({
      viewportWidthPx: 1920,
      textZoomPercent: 200,
    })
    // effective 960 → compact band
    expect(classifyShellViewport(1920 / 2)).toBe('compact')
    expect(at200.panelWidthPx).toBe(320)
    expect(assertShellLayoutNonOverlap(at200).ok).toBe(true)
  })
})

describe('Task 12: a11y Escape / scroll lock / return focus', () => {
  beforeEach(() => {
    resetShellFocusSessionsForTests()
    resetShellScrollLockForTests()
  })

  it('requires Chinese accessible names for shell chrome', () => {
    expect(assertChineseAccessibleName(SHELL_A11Y_NAMES['rail-trigger'])).toBe(true)
    expect(assertChineseAccessibleName('Formula')).toBe(false)
  })

  it('Escape closes one trap and restores focus; no dual trap', () => {
    const a = document.createElement('button')
    const b = document.createElement('button')
    document.body.append(a, b)
    beginShellFocusSession({ trapId: 't1', returnTarget: a })
    beginShellFocusSession({ trapId: 't2', returnTarget: b })
    // starting t2 ends t1
    expect(activeShellFocusTrapIds()).toEqual(['t2'])
    const ev = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })
    expect(handleShellEscapeKey(ev)).toBe(true)
    expect(activeShellFocusTrapIds()).toEqual([])
    endShellFocusSession('missing')
    a.remove()
    b.remove()
  })

  it('scroll lock is reference-counted', () => {
    acquireShellScrollLock()
    acquireShellScrollLock()
    expect(document.body.style.overflow).toBe('hidden')
    releaseShellScrollLock()
    expect(document.body.style.overflow).toBe('hidden')
    releaseShellScrollLock()
    expect(document.body.style.overflow).not.toBe('hidden')
  })
})

describe('Task 12: structured errors + safe log', () => {
  it('preserves work and strips sensitive payloads from logs', () => {
    const err = createShellStructuredError({
      domain: 'save',
      reasonCode: 'version_conflict',
      zhMessage: '保存冲突，请保留当前编辑后重试。',
      subjectKey: 'wp:1/sheet:s1',
      operation: 'batchMutate',
      provider: 'user-formula-v2',
      ownerEpoch: 2,
    })
    expect(err.preserveWork).toBe(true)
    const log = toShellSafeLog(err)
    expect(log).not.toHaveProperty('zhMessage')
    expect(log.reasonCode).toBe('version_conflict')
    expect(containsSensitiveShellPayload('formula==SUM(A1)')).toBe(true)
    expect(() =>
      createShellStructuredError({
        domain: 'provider',
        reasonCode: 'x',
        zhMessage: '失败 formula==SUM(A1)',
      }),
    ).toThrow(/sensitive/)
    expect(assertNotBroadCatchSuccess({ caught: true, reportedSuccess: true })).toEqual({
      ok: false,
      reasonCode: 'broad_catch_success_forbidden',
    })
  })

  it('parses live capability snapshot fail-closed on unknown major', () => {
    expect(
      parseCapabilitySnapshotPayload(
        { snapshotVersion: '9.0', ownerEpoch: 1, expiresAt: '2099-01-01T00:00:00Z' },
        1,
      ),
    ).toBeNull()
    const ok = parseCapabilitySnapshotPayload(
      {
        snapshotVersion: '1.0',
        subjectDigest: 'd',
        ownerEpoch: 3,
        expiresAt: '2099-01-01T00:00:00Z',
        formulaView: { allowed: true },
        formulaEditUser: { allowed: true },
        formulaHistory: { allowed: true },
        aiReviewPage: { allowed: true },
        aiReviewBatch: { allowed: true },
        aiAssistChat: { allowed: true },
        humanReviewRead: { allowed: true },
        humanReviewWrite: { allowed: true },
        guidanceRead: { allowed: true },
      },
      1,
    )
    expect(ok?.ownerEpoch).toBe(3)
  })
})

describe('Task 12: legacy cleanup scanners', () => {
  it('GtWpReviewRail no longer owns fixed placement', () => {
    const src = readFileSync(
      join(__dirname, '../../../components/workpaper/GtWpReviewRail.vue'),
      'utf8',
    )
    expect(scanFixedReviewRailSource(src, 'GtWpReviewRail.vue')).toEqual([])
    expect(src).toContain('WORKPAPER_SHELL_ACTIVE_KEY')
    // Style block must not declare fixed positioning (comments ignored by scanner).
    const style = src.slice(src.indexOf('<style'))
    const styleNoComments = style.replace(/\/\*[\s\S]*?\*\//g, '')
    expect(styleNoComments).not.toMatch(/position\s*:\s*fixed/i)
  })

  it('flags audit warning-then-commit and bare AI mounts', () => {
    expect(
      scanAuditWarningThenCommit(
        'except AuditCommitError:\n        pass  # warn-then-commit\n',
        'x.py',
      ),
    ).toHaveLength(1)
    expect(scanBareAiMount('openAiAssist()', 'x.ts')).toHaveLength(1)
    expect(scanHardcodedCapabilityAvailability('HARDCODED_CAPABILITY_ALLOW = true', 'x.ts')).toHaveLength(1)
  })

  it('ThreeColumnLayout provides DSH assist bridge', () => {
    const src = readFileSync(
      join(__dirname, '../../../layouts/ThreeColumnLayout.vue'),
      'utf8',
    )
    expect(src).toContain('DSH_ASSIST_BRIDGE_KEY')
    expect(src).toContain('provide(DSH_ASSIST_BRIDGE_KEY')
  })

  it('shell vue owns focus-visible + Escape + viewport media queries', () => {
    const src = readFileSync(
      join(__dirname, '../WorkpaperCapabilityShell.vue'),
      'utf8',
    )
    expect(src).toContain('focus-visible')
    expect(src).toContain('Escape')
    expect(src).toContain('min-width: 1280px')
    expect(src).toContain('min-width: 1440px')
    expect(src).toContain('min-width: 1920px')
  })
})
