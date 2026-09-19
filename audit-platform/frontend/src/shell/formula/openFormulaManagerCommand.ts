/**
 * OpenFormulaManagerCommand + dirty draft pin (formula-toolbar Task 6).
 *
 * Page entry opens the workpaper-route FormulaManager via this command —
 * never FormulaEditDialog. legacyNodeKey is migration metadata only.
 */

import type { CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import { assertLocationIdentity } from '@/shared/contracts/gc0/workpaper-route-baseline'

import {
  assertCapabilityAllowed,
  type WorkpaperCapabilitySnapshot,
} from './workpaperCapabilitySnapshot'

export const OPEN_FORMULA_MANAGER_COMMAND_VERSION = '2.0' as const

export interface OpenFormulaManagerCommand {
  commandVersion: typeof OPEN_FORMULA_MANAGER_COMMAND_VERSION
  location: CanonicalWorkpaperLocation
  capabilitySnapshotVersion: string
  ownerEpoch: number
  contextRevision: number
  /** Migration metadata only — never location identity. */
  legacyNodeKey?: string
}

export type FormulaManagerEmptyState = 'empty' | 'partial' | 'blocked'

export interface FormulaManagerSession {
  openedAtLocation: CanonicalWorkpaperLocation
  pinnedLocation: CanonicalWorkpaperLocation
  dirty: boolean
  followLatestWhenClean: boolean
  banner: string | null
  emptyState: FormulaManagerEmptyState | null
}

export type OpenFormulaManagerResult =
  | { ok: true; session: FormulaManagerSession }
  | { ok: false; reasonCode: string; detail: string }

export function createOpenFormulaManagerCommand(input: {
  location: CanonicalWorkpaperLocation
  capability: WorkpaperCapabilitySnapshot
  legacyNodeKey?: string
}): OpenFormulaManagerResult {
  const identity = assertLocationIdentity(input.location)
  if (!identity) {
    return {
      ok: false,
      reasonCode: 'gc0_location_rejected',
      detail: 'CanonicalWorkpaperLocation failed G-C0 version gate',
    }
  }
  if (input.location.ownerEpoch !== input.capability.ownerEpoch) {
    return {
      ok: false,
      reasonCode: 'epoch_mismatch',
      detail: 'location ownerEpoch must match capability snapshot',
    }
  }
  const cap = assertCapabilityAllowed(
    input.capability,
    'formulaView',
    input.location.ownerEpoch,
  )
  if (cap.status !== 'allowed') {
    return {
      ok: false,
      reasonCode: `capability_${cap.reasonCode}`,
      detail: cap.zhMessage,
    }
  }
  const command: OpenFormulaManagerCommand = {
    commandVersion: OPEN_FORMULA_MANAGER_COMMAND_VERSION,
    location: input.location,
    capabilitySnapshotVersion: input.capability.snapshotVersion,
    ownerEpoch: input.location.ownerEpoch,
    contextRevision: input.location.contextRevision,
    legacyNodeKey: input.legacyNodeKey,
  }
  return {
    ok: true,
    session: openSessionFromCommand(command),
  }
}

export function openSessionFromCommand(
  command: OpenFormulaManagerCommand,
): FormulaManagerSession {
  return {
    openedAtLocation: command.location,
    pinnedLocation: command.location,
    dirty: false,
    followLatestWhenClean: true,
    banner: null,
    emptyState: null,
  }
}

/**
 * Location change while dialog is open.
 * clean → follow latest; dirty → keep pin + banner.
 */
export function onLocationChangedWhileOpen(
  session: FormulaManagerSession,
  latest: CanonicalWorkpaperLocation,
): FormulaManagerSession {
  if (!session.dirty && session.followLatestWhenClean) {
    return {
      ...session,
      openedAtLocation: latest,
      pinnedLocation: latest,
      banner: null,
    }
  }
  return {
    ...session,
    openedAtLocation: latest,
    // pinnedLocation unchanged
    banner: '底稿位置已变化，草稿仍固定在原位置。保存将写入固定位置并重新校验权限。',
  }
}

export function markSessionDirty(session: FormulaManagerSession): FormulaManagerSession {
  return { ...session, dirty: true }
}

export function discardDraftAndFollowLatest(
  session: FormulaManagerSession,
): FormulaManagerSession {
  return {
    ...session,
    dirty: false,
    followLatestWhenClean: true,
    pinnedLocation: session.openedAtLocation,
    banner: null,
  }
}

export type SaveDraftDecision =
  | { allow: true; location: CanonicalWorkpaperLocation }
  | { allow: false; reasonCode: string; detail: string }

/**
 * Save always targets pinned location and revalidates capability + base version.
 */
export function decideSaveDraft(input: {
  session: FormulaManagerSession
  capability: WorkpaperCapabilitySnapshot | null | undefined
  routeOwnerValid: boolean
  baseVersionOk: boolean
}): SaveDraftDecision {
  if (!input.routeOwnerValid) {
    return {
      allow: false,
      reasonCode: 'route_owner_invalid',
      detail: '路由所有者已失效，仅允许导出或丢弃草稿',
    }
  }
  const cap = assertCapabilityAllowed(
    input.capability,
    'formulaEditUser',
    input.session.pinnedLocation.ownerEpoch,
  )
  if (cap.status !== 'allowed') {
    return {
      allow: false,
      reasonCode: `capability_${cap.reasonCode}`,
      detail: cap.status === 'blocked' ? cap.zhMessage : '无权保存',
    }
  }
  if (!input.baseVersionOk) {
    return {
      allow: false,
      reasonCode: 'base_version_stale',
      detail: '底稿版本已变化，请刷新后重试',
    }
  }
  return { allow: true, location: input.session.pinnedLocation }
}

/** Page entry must open FormulaManager — never FormulaEditDialog. */
export type FormulaPageEntryTarget = 'formula-manager' | 'formula-edit'

export function resolvePageEntryTarget(_source: 'toolbar' | 'nav' | 'command'): FormulaPageEntryTarget {
  return 'formula-manager'
}

/**
 * Legacy EventBus payload adapter — nodeKey is metadata only.
 */
export function legacyPayloadToPartialCommand(payload: {
  nodeKey?: string
}): { legacyNodeKey?: string } {
  return payload.nodeKey ? { legacyNodeKey: payload.nodeKey } : {}
}

export function emptyStateForAggregate(
  status: 'complete' | 'partial' | 'blocked' | 'empty',
): FormulaManagerEmptyState | null {
  if (status === 'complete') return null
  if (status === 'empty') return 'empty'
  if (status === 'partial') return 'partial'
  return 'blocked'
}
