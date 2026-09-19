/**
 * Runtime adapter registration telemetry for host inventory (Task 2).
 *
 * Inventory merges this with registry / render-config / custom entries.
 * Grep hits and CSS class names are NEVER written here — only explicit
 * adapter registration calls count as mounted capability facts.
 */

export type HostAdapterKind = 'html' | 'univer' | 'onlyoffice' | 'grid' | 'word'

export type OutletSupport = 'supported' | 'unsupported' | 'pending'

export interface HostAdapterTelemetryFact {
  hostInstanceId: string
  componentType: string | null
  host: HostAdapterKind
  primaryOutlet: OutletSupport
  compatibilityOutlet: OutletSupport
  /** True only when a real Vue named slot / outlet element was registered. */
  namedOutletMounted: boolean
  /** Slot name when namedOutletMounted; never a CSS class selector. */
  namedOutletSlot: string | null
  registeredAt: number
  source: 'toolbar-host-adapter' | 'renderer-host' | 'custom-runtime' | 'test'
}

const facts = new Map<string, HostAdapterTelemetryFact>()

export function resetHostAdapterTelemetry(): void {
  facts.clear()
}

export function registerHostAdapterTelemetry(fact: HostAdapterTelemetryFact): void {
  if (!fact.namedOutletMounted && fact.namedOutletSlot) {
    throw new Error(
      'hostAdapterTelemetry: namedOutletSlot requires namedOutletMounted=true',
    )
  }
  if (fact.namedOutletSlot && fact.namedOutletSlot.startsWith('.')) {
    throw new Error(
      'hostAdapterTelemetry: CSS class selectors are not named outlets',
    )
  }
  facts.set(fact.hostInstanceId, fact)
}

export function unregisterHostAdapterTelemetry(hostInstanceId: string): void {
  facts.delete(hostInstanceId)
}

export function listHostAdapterTelemetry(): HostAdapterTelemetryFact[] {
  return [...facts.values()].sort((a, b) =>
    a.hostInstanceId.localeCompare(b.hostInstanceId),
  )
}
