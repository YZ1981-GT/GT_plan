/**
 * Right-rail arbiter — formula-toolbar Task 11.
 *
 * Single-open arbitration for review → guidance → ai-assist.
 * Invisible / epoch-stale / capability-denied adapters never occupy DOM slots.
 */

import { assertRailIdentity } from '@/shared/contracts/gc0/workpaper-route-baseline'
import {
  createGuidanceRailAdapter,
  toGuidanceRailContractSnapshot,
  type GuidanceRailController,
  type RuntimeGuidanceRailAdapter,
} from '@/shell/guidance'
import type { CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import { assertCapabilityAllowed, type WorkpaperCapabilitySnapshot } from './workpaperCapabilitySnapshot'

export const SHELL_RAIL_ORDER = {
  review: 10,
  guidance: 20,
  'ai-assist': 30,
} as const

export type ShellRailId = keyof typeof SHELL_RAIL_ORDER

export interface ShellRailAdapter {
  id: ShellRailId
  order: number
  visible: boolean
  disabledReason: string | null
  ownerEpoch: number
  capabilityEpoch: number
  hasDraft: boolean
  a11yName: string
  open: () => void | Promise<void>
  close: (options: { preserveDraft: boolean }) => void | Promise<void>
  /** Guidance only — contract snapshot for G-RAIL consumption evidence. */
  guidanceContract?: RuntimeGuidanceRailAdapter | null
}

export type RailOpenState =
  | { status: 'closed' }
  | { status: 'open'; id: ShellRailId }

export interface RightRailLayoutSlot {
  id: ShellRailId
  occupiesSlot: boolean
  reasonCode: string | null
}

function isMountable(rail: ShellRailAdapter, activeCapabilityEpoch: number, activeOwnerEpoch: number): boolean {
  if (!rail.visible) return false
  if (rail.disabledReason) return false
  if (rail.capabilityEpoch !== activeCapabilityEpoch) return false
  if (rail.ownerEpoch !== activeOwnerEpoch) return false
  return true
}

export class RightRailArbiter {
  private rails = new Map<ShellRailId, ShellRailAdapter>()
  private openState: RailOpenState = { status: 'closed' }
  private activeCapabilityEpoch = 0
  private activeOwnerEpoch = 0

  setEpochs(input: { ownerEpoch: number; capabilityEpoch: number }): void {
    const ownerChanged = input.ownerEpoch !== this.activeOwnerEpoch
    const capChanged = input.capabilityEpoch !== this.activeCapabilityEpoch
    this.activeOwnerEpoch = input.ownerEpoch
    this.activeCapabilityEpoch = input.capabilityEpoch
    if ((ownerChanged || capChanged) && this.openState.status === 'open') {
      const open = this.rails.get(this.openState.id)
      if (!open || !isMountable(open, this.activeCapabilityEpoch, this.activeOwnerEpoch)) {
        void this.forceCloseOpen({ preserveDraft: true })
      }
    }
  }

  register(rail: ShellRailAdapter): { ok: true } | { ok: false; reasonCode: string } {
    if (rail.order !== SHELL_RAIL_ORDER[rail.id]) {
      return { ok: false, reasonCode: 'order_mismatch' }
    }
    this.rails.set(rail.id, rail)
    return { ok: true }
  }

  unregister(id: ShellRailId): void {
    if (this.openState.status === 'open' && this.openState.id === id) {
      void this.forceCloseOpen({ preserveDraft: true })
    }
    this.rails.delete(id)
  }

  getOpenState(): RailOpenState {
    return this.openState
  }

  listOrdered(): ShellRailAdapter[] {
    return [...this.rails.values()].sort((a, b) => a.order - b.order)
  }

  /** Triggers that may render — visible=false / stale / denied never occupy a slot. */
  listTriggerSlots(): RightRailLayoutSlot[] {
    return this.listOrdered().map((rail) => {
      if (!rail.visible) {
        return { id: rail.id, occupiesSlot: false, reasonCode: 'invisible' }
      }
      if (rail.disabledReason) {
        return { id: rail.id, occupiesSlot: false, reasonCode: 'denied' }
      }
      if (rail.capabilityEpoch !== this.activeCapabilityEpoch) {
        return { id: rail.id, occupiesSlot: false, reasonCode: 'capability_epoch_stale' }
      }
      if (rail.ownerEpoch !== this.activeOwnerEpoch) {
        return { id: rail.id, occupiesSlot: false, reasonCode: 'owner_epoch_stale' }
      }
      return { id: rail.id, occupiesSlot: true, reasonCode: null }
    })
  }

  mountableTriggers(): ShellRailAdapter[] {
    return this.listOrdered().filter((r) =>
      isMountable(r, this.activeCapabilityEpoch, this.activeOwnerEpoch),
    )
  }

  async requestOpen(id: ShellRailId): Promise<{ ok: boolean; reasonCode?: string }> {
    const rail = this.rails.get(id)
    if (!rail) return { ok: false, reasonCode: 'not_registered' }
    if (!isMountable(rail, this.activeCapabilityEpoch, this.activeOwnerEpoch)) {
      return { ok: false, reasonCode: 'not_mountable' }
    }
    if (this.openState.status === 'open' && this.openState.id !== id) {
      const prev = this.rails.get(this.openState.id)
      if (prev) await prev.close({ preserveDraft: true })
      this.openState = { status: 'closed' }
    }
    await rail.open()
    this.openState = { status: 'open', id }
    return { ok: true }
  }

  async requestClose(
    id: ShellRailId,
    options: { preserveDraft: boolean },
  ): Promise<{ ok: boolean; reasonCode?: string }> {
    const rail = this.rails.get(id)
    if (!rail) return { ok: false, reasonCode: 'not_registered' }
    if (this.openState.status !== 'open' || this.openState.id !== id) {
      return { ok: false, reasonCode: 'not_open' }
    }
    await rail.close(options)
    this.openState = { status: 'closed' }
    return { ok: true }
  }

  /** Clear open id when an adapter closed itself (e.g. panel fold) without re-entering close(). */
  acknowledgeExternalClose(id: ShellRailId): void {
    if (this.openState.status === 'open' && this.openState.id === id) {
      this.openState = { status: 'closed' }
    }
  }

  private async forceCloseOpen(options: { preserveDraft: boolean }): Promise<void> {
    if (this.openState.status !== 'open') return
    const rail = this.rails.get(this.openState.id)
    if (rail) await rail.close(options)
    this.openState = { status: 'closed' }
  }
}

let activeArbiter: RightRailArbiter | null = null

export function getRightRailArbiter(): RightRailArbiter {
  if (!activeArbiter) activeArbiter = new RightRailArbiter()
  return activeArbiter
}

export function resetRightRailArbiter(): void {
  activeArbiter = new RightRailArbiter()
}

/** Human review rail — unified provider only; no fixed-offset host rails. */
export function createReviewShellRail(input: {
  ownerEpoch: number
  capabilityEpoch: number
  snapshot: WorkpaperCapabilitySnapshot
  hasDraft: boolean
  open: () => void | Promise<void>
  close: (options: { preserveDraft: boolean }) => void | Promise<void>
}): ShellRailAdapter {
  const gate = assertCapabilityAllowed(input.snapshot, 'humanReviewRead', input.ownerEpoch)
  const allowed = gate.status === 'allowed'
  return {
    id: 'review',
    order: SHELL_RAIL_ORDER.review,
    visible: allowed,
    disabledReason: allowed ? null : (gate.status === 'blocked' ? gate.zhMessage : '无权查看底稿复核'),
    ownerEpoch: input.ownerEpoch,
    capabilityEpoch: input.capabilityEpoch,
    hasDraft: input.hasDraft,
    a11yName: '底稿复核',
    open: input.open,
    close: input.close,
  }
}

/** Guidance rail — import G-RAIL only; never redefine adapter. */
export function createGuidanceShellRail(input: {
  ownerEpoch: number
  capabilityEpoch: number
  snapshot: WorkpaperCapabilitySnapshot
  location: CanonicalWorkpaperLocation | null
  controller: GuidanceRailController
  visible?: boolean
  disabledReason?: string | null
}): ShellRailAdapter | null {
  const gate = assertCapabilityAllowed(input.snapshot, 'guidanceRead', input.ownerEpoch)
  const allowed = gate.status === 'allowed'
  const runtime = createGuidanceRailAdapter({
    location: input.location,
    visible: input.visible ?? true,
    disabledReason: input.disabledReason
      ?? (allowed ? null : (gate.status === 'blocked' ? gate.zhMessage : '无权查看编制说明')),
    capabilityAllowed: allowed,
    controller: input.controller,
  })
  if (!runtime) return null
  const identity = assertRailIdentity(toGuidanceRailContractSnapshot(runtime))
  if (!identity) return null
  return {
    id: 'guidance',
    order: SHELL_RAIL_ORDER.guidance,
    visible: runtime.visible,
    disabledReason: runtime.disabledReason,
    ownerEpoch: input.ownerEpoch,
    capabilityEpoch: input.capabilityEpoch,
    hasDraft: runtime.hasDraft,
    a11yName: '编制说明',
    open: () => runtime.open(),
    close: (opts) => runtime.close(opts),
    guidanceContract: runtime,
  }
}

/**
 * AI assist rail — DSH / PlatformAiChatPanel only.
 * Opening does not create a second shell panel; it toggles the DSH carrier.
 */
export function createAiAssistShellRail(input: {
  ownerEpoch: number
  capabilityEpoch: number
  snapshot: WorkpaperCapabilitySnapshot
  openDsh: () => void | Promise<void>
  closeDsh: (options: { preserveDraft: boolean }) => void | Promise<void>
  hasDraft?: boolean
}): ShellRailAdapter {
  const gate = assertCapabilityAllowed(input.snapshot, 'aiAssistChat', input.ownerEpoch)
  const allowed = gate.status === 'allowed'
  return {
    id: 'ai-assist',
    order: SHELL_RAIL_ORDER['ai-assist'],
    visible: allowed,
    disabledReason: allowed ? null : (gate.status === 'blocked' ? gate.zhMessage : '无权使用 AI 助手'),
    ownerEpoch: input.ownerEpoch,
    capabilityEpoch: input.capabilityEpoch,
    hasDraft: input.hasDraft ?? false,
    a11yName: 'AI 助手对话',
    open: () => input.openDsh(),
    close: (opts) => input.closeDsh(opts),
  }
}
