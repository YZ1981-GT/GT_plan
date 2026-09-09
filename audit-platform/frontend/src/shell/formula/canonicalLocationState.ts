/**
 * CanonicalLocationState runtime — formula-toolbar Task 4.
 *
 * Single owner reducer for workpaper-route location. Host adapters dispatch
 * stable facts only; this module alone publishes ready C0 snapshots.
 */

import {
  GC0_CONTRACT_VERSION,
  type CanonicalWorkpaperLocation,
  type StableLocationAnchor,
  type WorkpaperHost,
} from '@/shared/contracts/gc0'
import { assertLocationIdentity } from '@/shared/contracts/gc0/workpaper-route-baseline'

import { assertCapabilityAllowed, type WorkpaperCapabilitySnapshot } from './workpaperCapabilitySnapshot'
import { assertGidSheetIdentity } from './gidSheetIdentity'

export type CanonicalLocationState =
  | { status: 'uninitialized'; ownerEpoch: number; ownerKey: string | null }
  | { status: 'blocked'; ownerEpoch: number; ownerKey: string; reasonCode: string; detail: string }
  | {
      status: 'ready'
      ownerEpoch: number
      ownerKey: string
      contextRevision: number
      location: CanonicalWorkpaperLocation
      subjectKey: string
    }

export type HostLocationFact =
  | { type: 'routeEnter'; ownerKey: string }
  | {
      type: 'activateWorkpaper'
      organizationId: string
      projectId: string
      fiscalYear: number
      wpId: string
      wpCode: string
      entryId: string | null
      host: WorkpaperHost
      capabilityReady: boolean
    }
  | {
      type: 'activateSheet'
      sheetUid: string
      sheetCode: string | null
      /** display only */
      sheetName?: string | null
      /** Forbidden if used as identity — triggers block */
      sheetIndexAsIdentity?: number | null
      nodeKeyAsIdentity?: string | null
    }
  | {
      type: 'activateSection'
      sheetUid: string | null
      sectionId: string
      sectionLabel?: string | null
      nodeKeyAsIdentity?: string | null
    }
  | {
      type: 'activateCell'
      sheetUid: string
      addrId: string | null
      rowKey: string | null
      columnKey: string | null
      a1: string | null
      sheetName?: string | null
      nodeKeyAsIdentity?: string | null
    }
  | {
      type: 'activateDocument'
      anchorId: string | null
      nodeKeyAsIdentity?: string | null
    }
  | { type: 'activateWholeWorkbook' }
  | { type: 'block'; reasonCode: string; detail: string }

export interface LocationBaseContext {
  organizationId: string
  projectId: string
  fiscalYear: number
  wpId: string
  wpCode: string
  entryId: string | null
  host: WorkpaperHost
}

export interface LocationReducerBag {
  state: CanonicalLocationState
  base: LocationBaseContext | null
}

export function createInitialLocationRuntime(): LocationReducerBag {
  return {
    state: { status: 'uninitialized', ownerEpoch: 0, ownerKey: null },
    base: null,
  }
}

function subjectKeyOf(location: CanonicalWorkpaperLocation): string {
  const a = location.anchor
  const anchorPart =
    a.kind === 'page'
      ? 'page'
      : a.kind === 'sheet'
        ? `sheet:${a.sheetUid}`
        : a.kind === 'section'
          ? `section:${a.sheetUid ?? ''}:${a.sectionId}`
          : a.kind === 'cell'
            ? `cell:${a.sheetUid}:${a.addrId ?? ''}:${a.a1 ?? ''}`
            : a.kind === 'document'
              ? `document:${a.anchorId ?? ''}`
              : 'whole_workbook'
  return `${location.organizationId}|${location.projectId}|${location.wpId}|${location.host}|${anchorPart}`
}

function buildLocation(
  base: LocationBaseContext,
  anchor: StableLocationAnchor,
  ownerEpoch: number,
  contextRevision: number,
  display: CanonicalWorkpaperLocation['display'],
): CanonicalWorkpaperLocation {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: base.organizationId,
    projectId: base.projectId,
    fiscalYear: base.fiscalYear,
    wpId: base.wpId,
    wpCode: base.wpCode,
    entryId: base.entryId,
    host: base.host,
    anchor,
    display,
    ownerEpoch,
    contextRevision,
  }
}

function publishReady(
  bag: LocationReducerBag,
  ownerKey: string,
  ownerEpoch: number,
  contextRevision: number,
  location: CanonicalWorkpaperLocation,
): LocationReducerBag {
  const identity = assertLocationIdentity(location)
  if (!identity) {
    return {
      ...bag,
      state: {
        status: 'blocked',
        ownerEpoch,
        ownerKey,
        reasonCode: 'gc0_version_rejected',
        detail: 'CanonicalWorkpaperLocation failed G-C0 version gate',
      },
    }
  }
  return {
    ...bag,
    state: {
      status: 'ready',
      ownerEpoch,
      ownerKey,
      contextRevision,
      location,
      subjectKey: subjectKeyOf(location),
    },
  }
}

function block(
  bag: LocationReducerBag,
  ownerKey: string,
  ownerEpoch: number,
  reasonCode: string,
  detail: string,
): LocationReducerBag {
  return {
    ...bag,
    state: { status: 'blocked', ownerEpoch, ownerKey, reasonCode, detail },
  }
}

function nextRevision(state: CanonicalLocationState, ownerKey: string): {
  ownerEpoch: number
  contextRevision: number
} {
  if (state.status === 'uninitialized') {
    return { ownerEpoch: state.ownerEpoch || 1, contextRevision: 1 }
  }
  if (state.ownerKey === ownerKey) {
    const rev =
      state.status === 'ready' ? state.contextRevision + 1 : 1
    return { ownerEpoch: state.ownerEpoch, contextRevision: Math.max(1, rev) }
  }
  // Should not reach here for same-owner path; owner change handled in routeEnter.
  return { ownerEpoch: state.ownerEpoch + 1, contextRevision: 1 }
}

/**
 * Pure reducer — only owner of CanonicalLocationState on the workpaper route.
 */
export function reduceLocationFact(
  bag: LocationReducerBag,
  fact: HostLocationFact,
): LocationReducerBag {
  if (fact.type === 'routeEnter') {
    const prevEpoch = bag.state.ownerEpoch
    const sameOwner = bag.state.ownerKey === fact.ownerKey
    if (sameOwner && bag.state.status !== 'uninitialized') {
      // Re-enter same owner: keep epoch, reset to uninitialized for re-bootstrap.
      return {
        state: {
          status: 'uninitialized',
          ownerEpoch: prevEpoch,
          ownerKey: fact.ownerKey,
        },
        base: null,
      }
    }
    return {
      state: {
        status: 'uninitialized',
        ownerEpoch: prevEpoch + 1,
        ownerKey: fact.ownerKey,
      },
      base: null,
    }
  }

  const ownerKey = bag.state.ownerKey
  if (!ownerKey) {
    return block(bag, '_pending', bag.state.ownerEpoch, 'owner_missing', 'routeEnter required before activate*')
  }

  if (fact.type === 'block') {
    return block(bag, ownerKey, bag.state.ownerEpoch, fact.reasonCode, fact.detail)
  }

  if (fact.type === 'activateWorkpaper') {
    if (!fact.capabilityReady) {
      return block(
        bag,
        ownerKey,
        bag.state.ownerEpoch || 1,
        'capability_not_ready',
        'WorkpaperCapabilitySnapshot must be ready before location ready',
      )
    }
    const base: LocationBaseContext = {
      organizationId: fact.organizationId,
      projectId: fact.projectId,
      fiscalYear: fact.fiscalYear,
      wpId: fact.wpId,
      wpCode: fact.wpCode,
      entryId: fact.entryId,
      host: fact.host,
    }
    const ownerEpoch = bag.state.ownerEpoch || 1
    const location = buildLocation(
      base,
      { kind: 'page' },
      ownerEpoch,
      1,
      { sheetName: null, sectionLabel: null },
    )
    return publishReady({ state: bag.state, base }, ownerKey, ownerEpoch, 1, location)
  }

  if (!bag.base) {
    return block(
      bag,
      ownerKey,
      bag.state.ownerEpoch,
      'base_missing',
      'activateWorkpaper required before sheet/cell/document facts',
    )
  }

  const { ownerEpoch, contextRevision } = nextRevision(bag.state, ownerKey)

  if (fact.type === 'activateSheet') {
    const gid = assertGidSheetIdentity({
      sheetUid: fact.sheetUid,
      sheetCode: fact.sheetCode,
      sheetIndexAsIdentity: fact.sheetIndexAsIdentity,
      nodeKeyAsIdentity: fact.nodeKeyAsIdentity,
      // sheetName is display-only — do not pass as identity
    })
    if (!gid.ok) return block(bag, ownerKey, ownerEpoch, gid.reasonCode, gid.detail)
    const location = buildLocation(
      bag.base,
      { kind: 'sheet', sheetUid: gid.sheetUid, sheetCode: gid.sheetCode },
      ownerEpoch,
      contextRevision,
      { sheetName: fact.sheetName ?? null, sectionLabel: null },
    )
    return publishReady(bag, ownerKey, ownerEpoch, contextRevision, location)
  }

  if (fact.type === 'activateSection') {
    if (fact.nodeKeyAsIdentity) {
      return block(bag, ownerKey, ownerEpoch, 'gid_nodekey_not_identity', 'nodeKey is not section identity')
    }
    if (!fact.sectionId?.trim()) {
      return block(bag, ownerKey, ownerEpoch, 'section_id_missing', 'sectionId required')
    }
    if (fact.sheetUid) {
      const gid = assertGidSheetIdentity({ sheetUid: fact.sheetUid })
      if (!gid.ok) return block(bag, ownerKey, ownerEpoch, gid.reasonCode, gid.detail)
    }
    const location = buildLocation(
      bag.base,
      {
        kind: 'section',
        sheetUid: fact.sheetUid,
        sectionId: fact.sectionId.trim(),
      },
      ownerEpoch,
      contextRevision,
      { sheetName: null, sectionLabel: fact.sectionLabel ?? null },
    )
    return publishReady(bag, ownerKey, ownerEpoch, contextRevision, location)
  }

  if (fact.type === 'activateCell') {
    const gid = assertGidSheetIdentity({
      sheetUid: fact.sheetUid,
      nodeKeyAsIdentity: fact.nodeKeyAsIdentity,
    })
    if (!gid.ok) return block(bag, ownerKey, ownerEpoch, gid.reasonCode, gid.detail)
    const location = buildLocation(
      bag.base,
      {
        kind: 'cell',
        sheetUid: gid.sheetUid,
        addrId: fact.addrId,
        rowKey: fact.rowKey,
        columnKey: fact.columnKey,
        a1: fact.a1,
      },
      ownerEpoch,
      contextRevision,
      { sheetName: fact.sheetName ?? null, sectionLabel: null },
    )
    return publishReady(bag, ownerKey, ownerEpoch, contextRevision, location)
  }

  if (fact.type === 'activateDocument') {
    if (fact.nodeKeyAsIdentity) {
      return block(bag, ownerKey, ownerEpoch, 'gid_nodekey_not_identity', 'nodeKey is not document identity')
    }
    const location = buildLocation(
      bag.base,
      { kind: 'document', anchorId: fact.anchorId },
      ownerEpoch,
      contextRevision,
      { sheetName: null, sectionLabel: null },
    )
    return publishReady(bag, ownerKey, ownerEpoch, contextRevision, location)
  }

  if (fact.type === 'activateWholeWorkbook') {
    const location = buildLocation(
      bag.base,
      { kind: 'whole_workbook' },
      ownerEpoch,
      contextRevision,
      { sheetName: null, sectionLabel: null },
    )
    return publishReady(bag, ownerKey, ownerEpoch, contextRevision, location)
  }

  return bag
}

export interface AsyncLandingTicket {
  subjectKey: string
  ownerEpoch: number
  contextRevision: number
}

/**
 * Async result landing gate (Req 2.5 / 2.6):
 * same subject ∧ same ownerEpoch ∧ same contextRevision ∧ capability still valid.
 */
export function acceptAsyncLanding(args: {
  state: CanonicalLocationState
  ticket: AsyncLandingTicket
  capability: WorkpaperCapabilitySnapshot | null | undefined
  capabilityKey?: 'formulaView'
  now?: Date
}): { accept: true } | { accept: false; reasonCode: string } {
  if (args.state.status !== 'ready') {
    return { accept: false, reasonCode: 'location_not_ready' }
  }
  if (args.state.subjectKey !== args.ticket.subjectKey) {
    return { accept: false, reasonCode: 'subject_mismatch' }
  }
  if (args.state.ownerEpoch !== args.ticket.ownerEpoch) {
    return { accept: false, reasonCode: 'epoch_mismatch' }
  }
  if (args.state.contextRevision !== args.ticket.contextRevision) {
    return { accept: false, reasonCode: 'revision_mismatch' }
  }
  const cap = assertCapabilityAllowed(
    args.capability,
    args.capabilityKey ?? 'formulaView',
    args.state.ownerEpoch,
    args.now ?? new Date(),
  )
  if (cap.status !== 'allowed') {
    return { accept: false, reasonCode: `capability_${cap.reasonCode}` }
  }
  return { accept: true }
}

/** Convenience: current ready location or null. */
export function readyLocationOf(
  state: CanonicalLocationState,
): CanonicalWorkpaperLocation | null {
  return state.status === 'ready' ? state.location : null
}
