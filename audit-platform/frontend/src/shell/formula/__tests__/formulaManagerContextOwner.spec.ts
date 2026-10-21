import { describe, expect, it } from 'vitest'

import type { CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import type { OpenFormulaManagerPayload } from '@/utils/eventBus'
import {
  discardDraftAndFollowLatest,
  markSessionDirty,
  openSessionFromCommand,
} from '@/shell/formula/openFormulaManagerCommand'
import {
  receiveFormulaManagerOpen,
  receiveFormulaManagerSession,
} from '@/shell/formula/formulaManagerContextOwner'

function location(wpId: string, revision: number): CanonicalWorkpaperLocation {
  return {
    contractVersion: '1.0', organizationId: 'org', projectId: 'project', fiscalYear: 2025,
    wpId, wpCode: wpId === 'wp-a' ? 'A1' : 'D2-1', entryId: null, host: 'html',
    anchor: { kind: 'page' }, display: { sheetName: null, sectionLabel: null },
    ownerEpoch: 1, contextRevision: revision,
  }
}

function payload(wpId: string, revision: number): OpenFormulaManagerPayload {
  const loc = location(wpId, revision)
  return {
    contextKind: 'workpaper', scope: 'workpaper', projectId: loc.projectId,
    wpId: loc.wpId, wpCode: loc.wpCode, year: loc.fiscalYear,
    canonicalLocation: loc,
    formulaSession: openSessionFromCommand({
      commandVersion: '2.0', location: loc, capabilitySnapshotVersion: '1.0',
      ownerEpoch: 1, contextRevision: revision,
    }),
  }
}

describe('formulaManagerContextOwner', () => {
  it('clean 会话跟随最新底稿上下文', () => {
    const first = receiveFormulaManagerOpen({}, payload('wp-a', 1))
    const moved = receiveFormulaManagerOpen(first, payload('wp-b', 2))
    expect(moved.active?.wpId).toBe('wp-b')
    expect(moved.pending).toBeUndefined()
  })

  it('dirty 会话固定完整活动上下文，清除草稿后才切换 pending', () => {
    const first = receiveFormulaManagerOpen({}, payload('wp-a', 1))
    const dirty = markSessionDirty(first.active!.formulaSession!)
    const pinned = receiveFormulaManagerSession(first, dirty)
    const moved = receiveFormulaManagerOpen(pinned, payload('wp-b', 2))

    expect(moved.active?.wpId).toBe('wp-a')
    expect(moved.active?.formulaSession?.pinnedLocation.wpId).toBe('wp-a')
    expect(moved.active?.formulaSession?.openedAtLocation.wpId).toBe('wp-b')
    expect(moved.active?.formulaSession?.banner).toMatch(/固定/)
    expect(moved.pending?.wpId).toBe('wp-b')

    const clean = discardDraftAndFollowLatest(moved.active!.formulaSession!)
    const followed = receiveFormulaManagerSession(moved, clean)
    expect(followed.active?.wpId).toBe('wp-b')
    expect(followed.pending).toBeUndefined()
  })

  it('dirty workpaper 收到域级事件时不伪造或替换 wpId', () => {
    const first = receiveFormulaManagerOpen({}, payload('wp-a', 1))
    const dirty = receiveFormulaManagerSession(
      first,
      markSessionDirty(first.active!.formulaSession!),
    )
    const scopePayload: OpenFormulaManagerPayload = {
      contextKind: 'scope', scope: 'consol_report', projectId: 'project', year: 2025,
    }
    const moved = receiveFormulaManagerOpen(dirty, scopePayload)
    expect(moved.active?.contextKind).toBe('workpaper')
    expect(moved.active?.wpId).toBe('wp-a')
    expect(moved.pending).toEqual(scopePayload)
  })
})
