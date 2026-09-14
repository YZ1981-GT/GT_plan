/**
 * Formula-toolbar Task 4 — CanonicalLocationState + G-ID consumption.
 */

import { describe, expect, it } from 'vitest'

import {
  acceptAsyncLanding,
  createInitialLocationRuntime,
  readyLocationOf,
  reduceLocationFact,
  type LocationReducerBag,
} from '@/shell/formula/canonicalLocationState'
import { buildStableSheetIdentity, assertGidSheetIdentity } from '@/shell/formula/gidSheetIdentity'
import type { WorkpaperCapabilitySnapshot, CapabilityDecision } from '@/shell/formula'

function decision(allowed: boolean): CapabilityDecision {
  return {
    allowed,
    reasonCode: allowed ? null : 'role_denied',
    owner: 'workpaper-capability-matrix',
    nextAction: allowed ? null : '联系项目负责人',
    zhMessage: allowed ? null : '当前角色无权执行此操作。',
  }
}

function capability(ownerEpoch: number): WorkpaperCapabilitySnapshot {
  return {
    snapshotVersion: '1.0',
    subjectDigest: 'b'.repeat(64),
    ownerEpoch,
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

function bootstrap(ownerKey = 'wp:D0'): LocationReducerBag {
  let bag = createInitialLocationRuntime()
  bag = reduceLocationFact(bag, { type: 'routeEnter', ownerKey })
  bag = reduceLocationFact(bag, {
    type: 'activateWorkpaper',
    organizationId: 'org1',
    projectId: 'p1',
    fiscalYear: 2026,
    wpId: 'wp-1',
    wpCode: 'D0',
    entryId: 'entry-1',
    host: 'html',
    capabilityReady: true,
  })
  return bag
}

describe('Task 4: G-ID sheet identity', () => {
  it('builds stable identity without using name/index as key', () => {
    const id = buildStableSheetIdentity({
      wpCode: 'D0',
      sheetUid: 'uid-1',
      sheetCode: 'D0-1',
      templateLineageId: 'lin',
      templateVersionId: 'ver',
    })
    expect(id.catalogKey).toBe('lin|ver|D0|uid-1')
    expect(id.nullReason).toBeNull()
  })

  it('rejects name/index/nodeKey as identity', () => {
    expect(assertGidSheetIdentity({ sheetUid: 'u1', sheetNameAsIdentity: '封面' }).ok).toBe(false)
    expect(assertGidSheetIdentity({ sheetUid: 'u1', sheetIndexAsIdentity: 0 }).ok).toBe(false)
    expect(assertGidSheetIdentity({ sheetUid: 'u1', nodeKeyAsIdentity: 'D0' }).ok).toBe(false)
    expect(assertGidSheetIdentity({ sheetUid: null }).ok).toBe(false)
    expect(assertGidSheetIdentity({ sheetUid: 'u1' }).ok).toBe(true)
  })
})

describe('Task 4: CanonicalLocationState reducer', () => {
  it('routeEnter → uninitialized; activateWorkpaper → ready page', () => {
    const bag = bootstrap()
    expect(bag.state.status).toBe('ready')
    if (bag.state.status !== 'ready') return
    expect(bag.state.ownerEpoch).toBe(1)
    expect(bag.state.contextRevision).toBe(1)
    expect(bag.state.location.anchor.kind).toBe('page')
    expect(bag.state.location.contractVersion).toBe('1.0')
  })

  it('ownerEpoch increases across owners; contextRevision increases within owner', () => {
    let bag = bootstrap('wp:A')
    const epochA = bag.state.status === 'ready' ? bag.state.ownerEpoch : -1

    bag = reduceLocationFact(bag, {
      type: 'activateSheet',
      sheetUid: 's1',
      sheetCode: 'A-1',
      sheetName: '明细',
    })
    expect(bag.state.status).toBe('ready')
    if (bag.state.status !== 'ready') return
    expect(bag.state.ownerEpoch).toBe(epochA)
    expect(bag.state.contextRevision).toBe(2)
    expect(bag.state.location.anchor.kind).toBe('sheet')
    expect(bag.state.location.display.sheetName).toBe('明细')

    bag = reduceLocationFact(bag, { type: 'routeEnter', ownerKey: 'wp:B' })
    expect(bag.state.status).toBe('uninitialized')
    expect(bag.state.ownerEpoch).toBe(epochA + 1)

    bag = reduceLocationFact(bag, {
      type: 'activateWorkpaper',
      organizationId: 'org1',
      projectId: 'p1',
      fiscalYear: 2026,
      wpId: 'wp-2',
      wpCode: 'B50',
      entryId: null,
      host: 'onlyoffice',
      capabilityReady: true,
    })
    expect(bag.state.status).toBe('ready')
    if (bag.state.status !== 'ready') return
    expect(bag.state.ownerEpoch).toBe(epochA + 1)
    expect(bag.state.contextRevision).toBe(1)
  })

  it('blocks capability-not-ready and G-ID identity violations', () => {
    let bag = createInitialLocationRuntime()
    bag = reduceLocationFact(bag, { type: 'routeEnter', ownerKey: 'wp:X' })
    bag = reduceLocationFact(bag, {
      type: 'activateWorkpaper',
      organizationId: 'org1',
      projectId: 'p1',
      fiscalYear: 2026,
      wpId: 'wp-x',
      wpCode: 'X',
      entryId: null,
      host: 'html',
      capabilityReady: false,
    })
    expect(bag.state.status).toBe('blocked')
    if (bag.state.status === 'blocked') {
      expect(bag.state.reasonCode).toBe('capability_not_ready')
    }

    bag = bootstrap()
    bag = reduceLocationFact(bag, {
      type: 'activateSheet',
      sheetUid: 's1',
      sheetCode: 'D0-1',
      sheetIndexAsIdentity: 2,
    })
    expect(bag.state.status).toBe('blocked')
    if (bag.state.status === 'blocked') {
      expect(bag.state.reasonCode).toBe('gid_index_not_identity')
    }

    bag = bootstrap()
    bag = reduceLocationFact(bag, {
      type: 'activateCell',
      sheetUid: 's1',
      addrId: null,
      rowKey: null,
      columnKey: null,
      a1: 'A1',
      nodeKeyAsIdentity: 'legacy',
    })
    expect(bag.state.status).toBe('blocked')
    if (bag.state.status === 'blocked') {
      expect(bag.state.reasonCode).toBe('gid_nodekey_not_identity')
    }
  })

  it('supports document / whole_workbook / section without label identity', () => {
    let bag = bootstrap()
    bag = reduceLocationFact(bag, { type: 'activateWholeWorkbook' })
    expect(readyLocationOf(bag.state)?.anchor.kind).toBe('whole_workbook')

    bag = reduceLocationFact(bag, { type: 'activateDocument', anchorId: 'hdr-1' })
    expect(readyLocationOf(bag.state)?.anchor.kind).toBe('document')

    bag = reduceLocationFact(bag, {
      type: 'activateSection',
      sheetUid: 's1',
      sectionId: 'sec-9',
      sectionLabel: '判断',
    })
    const loc = readyLocationOf(bag.state)
    expect(loc?.anchor.kind).toBe('section')
    expect(loc?.display.sectionLabel).toBe('判断')
  })

  it('async landing requires subject+epoch+revision+capability', () => {
    const bag = bootstrap()
    expect(bag.state.status).toBe('ready')
    if (bag.state.status !== 'ready') return

    const ticket = {
      subjectKey: bag.state.subjectKey,
      ownerEpoch: bag.state.ownerEpoch,
      contextRevision: bag.state.contextRevision,
    }
    expect(
      acceptAsyncLanding({
        state: bag.state,
        ticket,
        capability: capability(bag.state.ownerEpoch),
      }).accept,
    ).toBe(true)

    expect(
      acceptAsyncLanding({
        state: bag.state,
        ticket: { ...ticket, contextRevision: ticket.contextRevision + 1 },
        capability: capability(bag.state.ownerEpoch),
      }).accept,
    ).toBe(false)

    expect(
      acceptAsyncLanding({
        state: bag.state,
        ticket,
        capability: null,
      }).accept,
    ).toBe(false)

    const moved = reduceLocationFact(bag, {
      type: 'activateSheet',
      sheetUid: 's2',
      sheetCode: 'D0-2',
    })
    expect(
      acceptAsyncLanding({
        state: moved.state,
        ticket,
        capability: capability(bag.state.ownerEpoch),
      }).accept,
    ).toBe(false)
  })
})
