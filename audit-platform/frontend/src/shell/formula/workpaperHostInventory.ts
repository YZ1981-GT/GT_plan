/**
 * Dynamic workpaper host / outlet / duplicate inventory (formula-toolbar Task 2).
 *
 * Derives entries from:
 *   1. renderer registry (REGISTRY_LIST)
 *   2. render-config componentType observations (optional)
 *   3. host adapter telemetry (mounted named outlets only)
 *   4. runtime custom entries (optional)
 *
 * Does NOT treat CSS class names, component labels, or grep hits as mounted
 * capability. Domain-owned routes are exclusion evidence only.
 */

import { REGISTRY_LIST } from '@/components/workpaper/registry'
import { sha256Hex } from './sha256Hex'
import type { WorkpaperHost } from '@/shared/contracts/gc0'

import {
  DOMAIN_OWNED_FORMULA_EXCLUSIONS,
  type DomainOwnedExclusion,
} from './domainExclusions'
import {
  listHostAdapterTelemetry,
  type HostAdapterTelemetryFact,
  type OutletSupport,
} from './hostAdapterTelemetry'
import {
  PRIMARY_OUTLET_SLOT,
  COMPATIBILITY_OUTLET_SLOT,
  GT_WP_TOOLBAR_RIGHT_CSS_CLASS,
} from './outletSlots'

export {
  PRIMARY_OUTLET_SLOT,
  COMPATIBILITY_OUTLET_SLOT,
  GT_WP_TOOLBAR_RIGHT_CSS_CLASS,
}

export const HOST_INVENTORY_VERSION = '1.0' as const

export type LocationGranularity =
  | 'page'
  | 'sheet'
  | 'section'
  | 'cell'
  | 'document'
  | 'whole_workbook'

export type EvidenceState = 'observed' | 'derived' | 'blocked' | 'excluded'

export interface WorkpaperHostCapabilityRecord {
  inventoryVersion: typeof HOST_INVENTORY_VERSION
  entryId: string
  componentType: string
  routeScope: 'workpaper' | 'domain-owned'
  host: WorkpaperHost
  locationGranularity: LocationGranularity
  primaryOutlet: OutletSupport
  compatibilityOutlet: OutletSupport
  formulaProviders: string[]
  aiReview: boolean
  aiAssist: boolean
  humanReview: boolean
  guidanceRail: boolean
  reason: string | null
  sourceDigest: string
  evidenceState: EvidenceState
}

export interface DuplicateCapabilityFinding {
  kind:
    | 'ai-assist'
    | 'ai-review-panel'
    | 'human-review'
    | 'guidance-rail'
    | 'bare-ai'
    | 'fixed-offset-rail'
    | 'formula-entry'
  relativePath: string
  detail: string
}

export interface HostInventoryRun {
  inventoryVersion: typeof HOST_INVENTORY_VERSION
  generatedAt: string
  runId: string
  entries: WorkpaperHostCapabilityRecord[]
  domainExclusions: DomainOwnedExclusion[]
  duplicates: DuplicateCapabilityFinding[]
  outletBaseline: {
    primarySlotName: typeof PRIMARY_OUTLET_SLOT
    compatibilitySlotName: typeof COMPATIBILITY_OUTLET_SLOT
    cssClassNotSlot: typeof GT_WP_TOOLBAR_RIGHT_CSS_CLASS
    /** True only when telemetry reports a real named primary outlet. */
    primaryNamedOutletMounted: boolean
    compatibilityNamedOutletMounted: boolean
  }
  digests: {
    entries: string
    duplicates: string
    exclusions: string
    run: string
  }
}

export interface HostPolicyProjection {
  componentType: string
  hostPolicy: string
}

export interface RuntimeCustomInventoryEntry {
  entryId: string
  componentType: string
  host: WorkpaperHost
  locationGranularity?: LocationGranularity
  reason?: string | null
}

export interface BuildHostInventoryInput {
  /** component_capabilities / host_policy projections (render-config adjacent). */
  hostPolicies?: readonly HostPolicyProjection[]
  /** Observed componentTypes from live render-config responses. */
  renderConfigComponentTypes?: readonly string[]
  runtimeCustomEntries?: readonly RuntimeCustomInventoryEntry[]
  /** Inject telemetry for tests; default = live registry. */
  telemetry?: readonly HostAdapterTelemetryFact[]
  /** Inject duplicate findings from source scanners / fixtures. */
  duplicates?: readonly DuplicateCapabilityFinding[]
  now?: () => Date
  runId?: string
}

function stableJson(value: unknown): string {
  return JSON.stringify(value, (_k, v) => v, 0)
}

function mapHostPolicy(policy: string | undefined): {
  host: WorkpaperHost
  reason: string | null
} {
  switch ((policy || 'html').toLowerCase()) {
    case 'html':
      return { host: 'html', reason: null }
    case 'onlyoffice':
      return { host: 'onlyoffice', reason: null }
    case 'univer':
      return { host: 'univer', reason: null }
    case 'grid':
      return { host: 'grid', reason: null }
    case 'word':
    case 'word-template':
      return { host: 'word', reason: null }
    case 'confirmation':
      return {
        host: 'html',
        reason: 'host_policy=confirmation projected to html for shell inventory',
      }
    case 'redirect':
      return {
        host: 'html',
        reason: 'host_policy=redirect — shell inventory marks blocked placement',
      }
    default:
      return {
        host: 'html',
        reason: `unknown host_policy=${policy} — fail-closed to html+pending outlets`,
      }
  }
}

function defaultGranularity(host: WorkpaperHost): LocationGranularity {
  switch (host) {
    case 'word':
      return 'document'
    case 'onlyoffice':
    case 'univer':
      return 'sheet'
    case 'grid':
      return 'cell'
    default:
      return 'page'
  }
}

function outletFromTelemetry(
  componentType: string,
  telemetry: readonly HostAdapterTelemetryFact[],
): { primary: OutletSupport; compatibility: OutletSupport; reason: string | null } {
  const hits = telemetry.filter(
    (t) => t.componentType === componentType || t.componentType === null,
  )
  if (hits.length === 0) {
    return {
      primary: 'unsupported',
      compatibility: 'unsupported',
      reason:
        'no ToolbarHostAdapter telemetry — CSS class / grep is not mounted capability',
    }
  }
  const primaryMounted = hits.some(
    (h) =>
      h.namedOutletMounted &&
      h.namedOutletSlot === PRIMARY_OUTLET_SLOT &&
      h.primaryOutlet === 'supported',
  )
  const compatMounted = hits.some(
    (h) =>
      h.namedOutletMounted &&
      h.namedOutletSlot === COMPATIBILITY_OUTLET_SLOT &&
      h.compatibilityOutlet === 'supported',
  )
  return {
    primary: primaryMounted ? 'supported' : 'pending',
    compatibility: compatMounted ? 'supported' : 'pending',
    reason: primaryMounted
      ? null
      : 'adapter registered but named primary outlet not yet selected',
  }
}

function buildEntry(args: {
  entryId: string
  componentType: string
  hostPolicy: string | undefined
  telemetry: readonly HostAdapterTelemetryFact[]
  evidenceState: EvidenceState
}): WorkpaperHostCapabilityRecord {
  const mapped = mapHostPolicy(args.hostPolicy)
  const outlets = outletFromTelemetry(args.componentType, args.telemetry)
  const reasonParts = [mapped.reason, outlets.reason].filter(Boolean)
  const recordBase = {
    inventoryVersion: HOST_INVENTORY_VERSION,
    entryId: args.entryId,
    componentType: args.componentType,
    routeScope: 'workpaper' as const,
    host: mapped.host,
    locationGranularity: defaultGranularity(mapped.host),
    primaryOutlet: outlets.primary,
    compatibilityOutlet: outlets.compatibility,
    formulaProviders: [] as string[],
    aiReview: false,
    aiAssist: false,
    humanReview: false,
    guidanceRail: false,
    reason: reasonParts.length ? reasonParts.join('; ') : null,
    evidenceState: args.evidenceState,
  }
  const sourceDigest = sha256Hex(stableJson({ ...recordBase, sourceDigest: null }))
  return { ...recordBase, sourceDigest }
}

/**
 * Build a reproducible inventory run. Entry count comes from registry (+ custom),
 * never from a hardcoded page list.
 */
export function buildWorkpaperHostInventory(
  input: BuildHostInventoryInput = {},
): HostInventoryRun {
  const telemetry = input.telemetry ?? listHostAdapterTelemetry()
  const policyByType = new Map(
    (input.hostPolicies ?? []).map((p) => [p.componentType, p.hostPolicy]),
  )
  const observed = new Set(input.renderConfigComponentTypes ?? [])

  const entries: WorkpaperHostCapabilityRecord[] = []

  for (const reg of REGISTRY_LIST) {
    const evidenceState: EvidenceState = observed.has(reg.componentType)
      ? 'observed'
      : 'derived'
    entries.push(
      buildEntry({
        entryId: `registry:${reg.componentType}`,
        componentType: reg.componentType,
        hostPolicy: policyByType.get(reg.componentType),
        telemetry,
        evidenceState,
      }),
    )
  }

  for (const custom of input.runtimeCustomEntries ?? []) {
    const mapped = mapHostPolicy(policyByType.get(custom.componentType))
    const outlets = outletFromTelemetry(custom.componentType, telemetry)
    const recordBase = {
      inventoryVersion: HOST_INVENTORY_VERSION,
      entryId: custom.entryId,
      componentType: custom.componentType,
      routeScope: 'workpaper' as const,
      host: custom.host ?? mapped.host,
      locationGranularity:
        custom.locationGranularity ?? defaultGranularity(custom.host ?? mapped.host),
      primaryOutlet: outlets.primary,
      compatibilityOutlet: outlets.compatibility,
      formulaProviders: [] as string[],
      aiReview: false,
      aiAssist: false,
      humanReview: false,
      guidanceRail: false,
      reason: custom.reason ?? outlets.reason,
      evidenceState: 'observed' as const,
    }
    entries.push({
      ...recordBase,
      sourceDigest: sha256Hex(stableJson({ ...recordBase, sourceDigest: null })),
    })
  }

  entries.sort((a, b) => a.entryId.localeCompare(b.entryId))

  const duplicates = [...(input.duplicates ?? [])].sort((a, b) =>
    `${a.kind}:${a.relativePath}`.localeCompare(`${b.kind}:${b.relativePath}`),
  )

  const primaryNamedOutletMounted = telemetry.some(
    (t) =>
      t.namedOutletMounted &&
      t.namedOutletSlot === PRIMARY_OUTLET_SLOT &&
      t.primaryOutlet === 'supported',
  )
  const compatibilityNamedOutletMounted = telemetry.some(
    (t) =>
      t.namedOutletMounted &&
      t.namedOutletSlot === COMPATIBILITY_OUTLET_SLOT &&
      t.compatibilityOutlet === 'supported',
  )

  const now = (input.now ?? (() => new Date()))()
  const runId =
    input.runId ??
    sha256Hex(`${now.toISOString()}:${entries.length}:${duplicates.length}`).slice(0, 16)

  const digests = {
    entries: sha256Hex(stableJson(entries.map((e) => e.sourceDigest))),
    duplicates: sha256Hex(stableJson(duplicates)),
    exclusions: sha256Hex(stableJson(DOMAIN_OWNED_FORMULA_EXCLUSIONS)),
    run: '',
  }

  const runWithoutRunDigest: Omit<HostInventoryRun, 'digests'> & {
    digests: Omit<HostInventoryRun['digests'], 'run'>
  } = {
    inventoryVersion: HOST_INVENTORY_VERSION,
    generatedAt: now.toISOString(),
    runId,
    entries,
    domainExclusions: [...DOMAIN_OWNED_FORMULA_EXCLUSIONS],
    duplicates,
    outletBaseline: {
      primarySlotName: PRIMARY_OUTLET_SLOT,
      compatibilitySlotName: COMPATIBILITY_OUTLET_SLOT,
      cssClassNotSlot: GT_WP_TOOLBAR_RIGHT_CSS_CLASS,
      primaryNamedOutletMounted,
      compatibilityNamedOutletMounted,
    },
    digests: {
      entries: digests.entries,
      duplicates: digests.duplicates,
      exclusions: digests.exclusions,
    },
  }
  digests.run = sha256Hex(stableJson(runWithoutRunDigest))

  return {
    ...runWithoutRunDigest,
    digests: {
      entries: digests.entries,
      duplicates: digests.duplicates,
      exclusions: digests.exclusions,
      run: digests.run,
    },
  }
}

/**
 * Fail-closed: a CSS class string must never flip outlet support to supported.
 * Used by mounted red guards / mutations.
 */
export function assertCssClassIsNotOutletCapability(
  className: string,
  run: HostInventoryRun,
): void {
  if (className !== GT_WP_TOOLBAR_RIGHT_CSS_CLASS) {
    throw new Error(`unexpected class under assertion: ${className}`)
  }
  if (run.outletBaseline.cssClassNotSlot !== className) {
    throw new Error('outletBaseline.cssClassNotSlot drifted from frozen CSS class')
  }
  if (run.outletBaseline.primaryNamedOutletMounted && !run.entries.some((e) => e.primaryOutlet === 'supported')) {
    throw new Error('telemetry claims primary mounted but no entry is supported')
  }
  // Grep / class presence alone must not mark any entry supported when telemetry is empty.
  const telemetryEmpty = !run.outletBaseline.primaryNamedOutletMounted
  if (telemetryEmpty) {
    const supported = run.entries.filter((e) => e.primaryOutlet === 'supported')
    if (supported.length > 0) {
      throw new Error(
        `CSS/grep must not invent supported outlets; got ${supported.map((s) => s.entryId).join(',')}`,
      )
    }
  }
}
