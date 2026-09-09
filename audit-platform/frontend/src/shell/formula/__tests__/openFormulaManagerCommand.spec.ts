/**
 * Formula-toolbar Task 6 — OpenFormulaManagerCommand + dirty pin.
 */

import { describe, expect, it } from 'vitest'

import { GC0_CONTRACT_VERSION, type CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import type { WorkpaperCapabilitySnapshot, CapabilityDecision } from '@/shell/formula'
import {
  createOpenFormulaManagerCommand,
  onLocationChangedWhileOpen,
  markSessionDirty,
  discardDraftAndFollowLatest,
  decideSaveDraft,
  resolvePageEntryTarget,
  legacyPayloadToPartialCommand,
  emptyStateForAggregate,
} from '@/shell/formula/openFormulaManagerCommand'

function decision(allowed: boolean): CapabilityDecision {
  return {
    allowed,
    reasonCode: allowed ? null : 'role_denied',
    owner: 'workpaper-capability-matrix',
    nextAction: allowed ? null : '联系项目负责人',
    zhMessage: allowed ? null : '当前角色无权执行此操作。',
  }
}

function location(epoch = 1, rev = 1): CanonicalWorkpaperLocation {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: 'org',
    projectId: 'p1',
    fiscalYear: 2026,
    wpId: 'wp-1',
    wpCode: 'D0',
    entryId: 'e1',
    host: 'html',
    anchor: { kind: 'page' },
    display: { sheetName: null, sectionLabel: null },
    ownerEpoch: epoch,
    contextRevision: rev,
  }
}

function capability(epoch = 1): WorkpaperCapabilitySnapshot {
  return {
    snapshotVersion: '1.0',
    subjectDigest: 'c'.repeat(64),
    ownerEpoch: epoch,
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    formulaView: decision(true),
    formulaEditUser: decision(true),
    formulaHistory: decision(true),
    aiReviewPage: decision(true),
    aiReviewBatch: decision(true),
    aiAssistChat: decision(true),
    humanReviewRead: decision(true),
    humanReviewWrite: decision(true),
    guidanceRead: decision(true),
  }
}

describe('Task 6: OpenFormulaManagerCommand + dirty pin', () => {
  it('opens session with C0 location and capability epoch', () => {
    const result = createOpenFormulaManagerCommand({
      location: location(2, 3),
      capability: capability(2),
      legacyNodeKey: 'D0',
    })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.session.pinnedLocation.ownerEpoch).toBe(2)
    expect(result.session.dirty).toBe(false)
  })

  it('clean follows latest; dirty pins and shows banner', () => {
    const opened = createOpenFormulaManagerCommand({
      location: location(1, 1),
      capability: capability(1),
    })
    expect(opened.ok).toBe(true)
    if (!opened.ok) return

    const followed = onLocationChangedWhileOpen(opened.session, location(1, 2))
    expect(followed.pinnedLocation.contextRevision).toBe(2)
    expect(followed.banner).toBeNull()

    const dirty = markSessionDirty(followed)
    const pinned = onLocationChangedWhileOpen(dirty, location(1, 3))
    expect(pinned.pinnedLocation.contextRevision).toBe(2)
    expect(pinned.openedAtLocation.contextRevision).toBe(3)
    expect(pinned.banner).toMatch(/固定/)

    const discarded = discardDraftAndFollowLatest(pinned)
    expect(discarded.dirty).toBe(false)
    expect(discarded.pinnedLocation.contextRevision).toBe(3)
    expect(discarded.banner).toBeNull()
  })

  it('save uses pinned location and revalidates capability/base version', () => {
    const opened = createOpenFormulaManagerCommand({
      location: location(1, 1),
      capability: capability(1),
    })
    expect(opened.ok).toBe(true)
    if (!opened.ok) return
    const dirty = markSessionDirty(opened.session)
    const moved = onLocationChangedWhileOpen(dirty, location(1, 9))

    const ok = decideSaveDraft({
      session: moved,
      capability: capability(1),
      routeOwnerValid: true,
      baseVersionOk: true,
    })
    expect(ok.allow).toBe(true)
    if (ok.allow) expect(ok.location.contextRevision).toBe(1)

    const denied = decideSaveDraft({
      session: moved,
      capability: capability(1),
      routeOwnerValid: false,
      baseVersionOk: true,
    })
    expect(denied.allow).toBe(false)
  })

  it('page entry targets FormulaManager never FormulaEditDialog; nodeKey is metadata', () => {
    expect(resolvePageEntryTarget('toolbar')).toBe('formula-manager')
    expect(legacyPayloadToPartialCommand({ nodeKey: 'D0' })).toEqual({ legacyNodeKey: 'D0' })
    expect(emptyStateForAggregate('empty')).toBe('empty')
    expect(emptyStateForAggregate('blocked')).toBe('blocked')
    expect(emptyStateForAggregate('complete')).toBeNull()
  })
})
