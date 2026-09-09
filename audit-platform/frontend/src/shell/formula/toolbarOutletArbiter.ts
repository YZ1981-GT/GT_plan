/**
 * Toolbar outlet registration + placement arbiter (formula-toolbar Task 5).
 *
 * Primary wins; compatibility only when primary is explicitly unavailable.
 * Cross-epoch / duplicate kind / multi-primary ⇒ collision (no silent overwrite).
 */

import {
  COMPATIBILITY_OUTLET_SLOT,
  PRIMARY_OUTLET_SLOT,
} from './outletSlots'

export type ToolbarOutletKind = 'primary' | 'compatibility'

export interface ToolbarOutletRegistration {
  registrationId: string
  hostInstanceId: string
  ownerEpoch: number
  kind: ToolbarOutletKind
  /** Real outlet element (named slot mount point). Never a CSS-class-only node. */
  outletElement: HTMLElement
  namedSlot: typeof PRIMARY_OUTLET_SLOT | typeof COMPATIBILITY_OUTLET_SLOT
  mountedAt: number
  leaseToken: string
}

export type ToolbarPlacementState =
  | { status: 'pending'; ownerEpoch: number }
  | { status: 'registered'; selected: ToolbarOutletRegistration }
  | { status: 'blocked'; ownerEpoch: number; reasonCode: string; detail: string }

export interface ToolbarHostAdapter {
  hostInstanceId: string
  kind: ToolbarOutletKind
  namedSlot: typeof PRIMARY_OUTLET_SLOT | typeof COMPATIBILITY_OUTLET_SLOT
  /** When true, this host reports itself unavailable (e.g. not mounted). */
  unavailable?: boolean
}

function newLeaseToken(): string {
  return `lease-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export class ToolbarOutletArbiter {
  private ownerEpoch = 0
  private primaryUnavailable = false
  private readonly byKind = new Map<ToolbarOutletKind, ToolbarOutletRegistration>()
  private placement: ToolbarPlacementState = { status: 'pending', ownerEpoch: 0 }

  getPlacement(): ToolbarPlacementState {
    return this.placement
  }

  /** Begin a host render cycle — placement stays pending until settle(). */
  beginCycle(ownerEpoch: number): void {
    if (ownerEpoch !== this.ownerEpoch) {
      this.byKind.clear()
      this.primaryUnavailable = false
      this.ownerEpoch = ownerEpoch
    }
    this.placement = { status: 'pending', ownerEpoch }
  }

  markPrimaryUnavailable(ownerEpoch: number, unavailable = true): void {
    if (ownerEpoch !== this.ownerEpoch) {
      this.placement = {
        status: 'blocked',
        ownerEpoch,
        reasonCode: 'epoch_mismatch',
        detail: 'markPrimaryUnavailable across owner epoch',
      }
      return
    }
    this.primaryUnavailable = unavailable
  }

  register(input: {
    hostInstanceId: string
    ownerEpoch: number
    kind: ToolbarOutletKind
    outletElement: HTMLElement
    namedSlot: typeof PRIMARY_OUTLET_SLOT | typeof COMPATIBILITY_OUTLET_SLOT
    mountedAt?: number
  }): { ok: true; registration: ToolbarOutletRegistration } | { ok: false; reasonCode: string } {
    if (input.ownerEpoch !== this.ownerEpoch) {
      this.placement = {
        status: 'blocked',
        ownerEpoch: this.ownerEpoch,
        reasonCode: 'cross_epoch_registration',
        detail: `registration epoch ${input.ownerEpoch} ≠ active ${this.ownerEpoch}`,
      }
      return { ok: false, reasonCode: 'cross_epoch_registration' }
    }
    if (input.kind === 'primary' && input.namedSlot !== PRIMARY_OUTLET_SLOT) {
      return { ok: false, reasonCode: 'slot_kind_mismatch' }
    }
    if (input.kind === 'compatibility' && input.namedSlot !== COMPATIBILITY_OUTLET_SLOT) {
      return { ok: false, reasonCode: 'slot_kind_mismatch' }
    }
    // CSS class alone is not an outlet — require a real element with data attribute or tag.
    if (input.outletElement.classList?.contains('gt-wp-toolbar__right')
      && !input.outletElement.hasAttribute('data-toolbar-outlet')) {
      return { ok: false, reasonCode: 'css_class_not_outlet' }
    }
    const existing = this.byKind.get(input.kind)
    if (existing && existing.hostInstanceId !== input.hostInstanceId) {
      this.placement = {
        status: 'blocked',
        ownerEpoch: this.ownerEpoch,
        reasonCode: 'duplicate_kind_collision',
        detail: `kind=${input.kind} already registered by ${existing.hostInstanceId}`,
      }
      return { ok: false, reasonCode: 'duplicate_kind_collision' }
    }
    const registration: ToolbarOutletRegistration = {
      registrationId: `${input.kind}:${input.hostInstanceId}`,
      hostInstanceId: input.hostInstanceId,
      ownerEpoch: input.ownerEpoch,
      kind: input.kind,
      outletElement: input.outletElement,
      namedSlot: input.namedSlot,
      mountedAt: input.mountedAt ?? Date.now(),
      leaseToken: newLeaseToken(),
    }
    this.byKind.set(input.kind, registration)
    return { ok: true, registration }
  }

  unregister(hostInstanceId: string, ownerEpoch: number): void {
    if (ownerEpoch !== this.ownerEpoch) return
    for (const [kind, reg] of [...this.byKind.entries()]) {
      if (reg.hostInstanceId === hostInstanceId) this.byKind.delete(kind)
    }
    this.recompute()
  }

  /** End of host render cycle — pick primary, else compatibility if primary unavailable. */
  settle(): ToolbarPlacementState {
    this.recompute()
    return this.placement
  }

  private recompute(): void {
    if (this.placement.status === 'blocked'
      && (this.placement.reasonCode === 'duplicate_kind_collision'
        || this.placement.reasonCode === 'cross_epoch_registration')) {
      return
    }
    const primary = this.byKind.get('primary')
    const compat = this.byKind.get('compatibility')
    if (primary) {
      this.placement = { status: 'registered', selected: primary }
      return
    }
    if (this.primaryUnavailable && compat) {
      this.placement = { status: 'registered', selected: compat }
      return
    }
    if (compat && !this.primaryUnavailable) {
      // Fallback must not steal while primary is still pending/available.
      this.placement = { status: 'pending', ownerEpoch: this.ownerEpoch }
      return
    }
    if (!primary && !compat) {
      this.placement = {
        status: 'blocked',
        ownerEpoch: this.ownerEpoch,
        reasonCode: 'no_outlet_registered',
        detail: 'no primary or compatibility outlet',
      }
      return
    }
    this.placement = { status: 'pending', ownerEpoch: this.ownerEpoch }
  }
}

/** Process-local arbiter for the workpaper-route shell (tests may construct their own). */
let activeArbiter: ToolbarOutletArbiter | null = null

export function getToolbarOutletArbiter(): ToolbarOutletArbiter {
  if (!activeArbiter) activeArbiter = new ToolbarOutletArbiter()
  return activeArbiter
}

export function resetToolbarOutletArbiter(): void {
  activeArbiter = new ToolbarOutletArbiter()
}
