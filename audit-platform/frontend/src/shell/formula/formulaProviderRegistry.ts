/**
 * Orthogonal FormulaDescriptor + ProviderRegistry + AggregateResult (Task 7).
 */

import type { CanonicalWorkpaperLocation, StableLocationAnchor } from '@/shared/contracts/gc0'
import { sha256Hex } from './sha256Hex'

export type FormulaOrigin = 'platform' | 'user' | 'runtime_generated'
export type FormulaRuleKind =
  | 'data_fetch'
  | 'calculation'
  | 'logic_check'
  | 'reasonableness'
  | 'presentation'
export type FormulaEngine =
  | 'backend_formula'
  | 'user_formula_store'
  | 'auto_data_resolver'
  | 'frontend_formula_engine'
export type FormulaProtection = 'editable' | 'protected' | 'system_managed'

export type AnchorKind = StableLocationAnchor['kind']

export interface FormulaDescriptor {
  descriptorVersion: '2.0'
  formulaId: string
  semanticDigest: string
  origin: FormulaOrigin
  ruleKind: FormulaRuleKind
  engine: FormulaEngine
  protection: FormulaProtection
  location: CanonicalWorkpaperLocation
  target: {
    addrId: string | null
    fieldKey: string | null
    rowKey: string | null
    columnKey: string | null
    a1: string | null
  }
  formulaFunction: string | null
  ruleCategory: string
  expression: string | null
  ruleSummary: string
  refs: string[]
  currentValue: unknown
  valueStatus: 'resolved' | 'error' | 'unavailable' | 'stale'
  calculatedAt: string | null
  contextFingerprint: string
  manualOverride: boolean
  version: string
  owner: string
  protectionReason: string | null
  updatedBy: string | null
  updatedAt: string | null
  provenance: { providerId: string; sourceDigest: string }
  lineage?: {
    upstream: string[]
    downstream: string[]
    stale: boolean
  }
}

export type ProviderVerdict = 'ok' | 'unsupported' | 'error' | 'timeout'

export interface FormulaProviderResult {
  providerId: string
  verdict: ProviderVerdict
  reason: string | null
  descriptors: FormulaDescriptor[]
}

export interface FormulaAggregateResult {
  status: 'complete' | 'partial' | 'blocked'
  location: CanonicalWorkpaperLocation
  descriptors: FormulaDescriptor[]
  providerResults: Array<{
    providerId: string
    verdict: ProviderVerdict
    reason: string | null
  }>
  collisions: Array<{
    formulaId: string
    providerIds: string[]
    semanticDigests: string[]
  }>
  generatedAt: string
}

export interface FormulaProviderAdapter {
  providerId: string
  /** Declared anchor kinds this adapter can serve. */
  supports(anchorKind: AnchorKind): boolean
  query(location: CanonicalWorkpaperLocation): Promise<FormulaProviderResult> | FormulaProviderResult
}

export function semanticDigestOf(parts: Record<string, unknown>): string {
  const raw = JSON.stringify(parts, Object.keys(parts).sort())
  return sha256Hex(raw)
}

export function aggregateProviderResults(
  location: CanonicalWorkpaperLocation,
  results: FormulaProviderResult[],
  now: Date = new Date(),
): FormulaAggregateResult {
  const byId = new Map<string, FormulaDescriptor[]>()
  const providerResults = results.map((r) => ({
    providerId: r.providerId,
    verdict: r.verdict,
    reason: r.reason,
  }))

  for (const r of results) {
    if (r.verdict !== 'ok') continue
    for (const d of r.descriptors) {
      const list = byId.get(d.formulaId) ?? []
      list.push(d)
      byId.set(d.formulaId, list)
    }
  }

  const descriptors: FormulaDescriptor[] = []
  const collisions: FormulaAggregateResult['collisions'] = []

  for (const [formulaId, list] of byId) {
    const digests = [...new Set(list.map((d) => d.semanticDigest))]
    if (digests.length > 1) {
      collisions.push({
        formulaId,
        providerIds: list.map((d) => d.provenance.providerId),
        semanticDigests: digests,
      })
      continue
    }
    // Same digest → merge provenance note onto first
    descriptors.push(list[0])
  }

  const anyError = results.some((r) => r.verdict === 'error' || r.verdict === 'timeout')
  const anyUnsupportedAll =
    results.length > 0 && results.every((r) => r.verdict === 'unsupported')

  let status: FormulaAggregateResult['status'] = 'complete'
  if (collisions.length > 0 || anyUnsupportedAll) status = 'blocked'
  else if (anyError || results.some((r) => r.verdict === 'unsupported')) status = 'partial'

  return {
    status,
    location,
    descriptors,
    providerResults,
    collisions,
    generatedAt: now.toISOString(),
  }
}

export class FormulaProviderRegistry {
  private readonly adapters = new Map<string, FormulaProviderAdapter>()

  register(adapter: FormulaProviderAdapter): void {
    if (this.adapters.has(adapter.providerId)) {
      throw new Error(`duplicate formula provider: ${adapter.providerId}`)
    }
    this.adapters.set(adapter.providerId, adapter)
  }

  listProviderIds(): string[] {
    return [...this.adapters.keys()].sort()
  }

  async query(location: CanonicalWorkpaperLocation): Promise<FormulaAggregateResult> {
    const kind = location.anchor.kind
    const results: FormulaProviderResult[] = []
    for (const adapter of this.adapters.values()) {
      if (!adapter.supports(kind)) {
        results.push({
          providerId: adapter.providerId,
          verdict: 'unsupported',
          reason: `anchor kind ${kind} not supported`,
          descriptors: [],
        })
        continue
      }
      try {
        results.push(await adapter.query(location))
      } catch (err) {
        results.push({
          providerId: adapter.providerId,
          verdict: 'error',
          reason: err instanceof Error ? err.message : 'provider error',
          descriptors: [],
        })
      }
    }
    return aggregateProviderResults(location, results)
  }
}

/** Five truth-source adapters — project descriptors; do not copy stores. */
export function createDefaultFormulaProviderRegistry(
  factories?: Partial<Record<string, FormulaProviderAdapter>>,
): FormulaProviderRegistry {
  const reg = new FormulaProviderRegistry()
  const defaults: FormulaProviderAdapter[] = [
    factories?.platform ?? stubAdapter('platform', 'platform', 'backend_formula', 'protected'),
    factories?.user ?? stubAdapter('user', 'user', 'user_formula_store', 'editable'),
    factories?.auto_data ??
      stubAdapter('auto_data', 'runtime_generated', 'auto_data_resolver', 'system_managed'),
    factories?.logic_reasonableness ??
      stubAdapter('logic_reasonableness', 'platform', 'backend_formula', 'protected', 'logic_check'),
    factories?.frontend_engine ??
      stubAdapter('frontend_engine', 'platform', 'frontend_formula_engine', 'protected', 'calculation'),
  ]
  for (const a of defaults) reg.register(a)
  return reg
}

function stubAdapter(
  providerId: string,
  _origin: FormulaOrigin,
  _engine: FormulaEngine,
  _protection: FormulaProtection,
  _ruleKind: FormulaRuleKind = 'data_fetch',
): FormulaProviderAdapter {
  return {
    providerId,
    supports: () => true,
    query: () => ({
      providerId,
      verdict: 'ok',
      reason: null,
      descriptors: [],
    }),
  }
}

export interface LineageEnrichmentInput {
  aggregate: FormulaAggregateResult
  /** providerId → formulaId → { upstream, downstream } */
  linkage: Record<string, { upstream: string[]; downstream: string[]; stale?: boolean }>
  linkageFailed?: boolean
}

/**
 * Batch ACNR/linkage enrichment. Failure keeps descriptors and marks partial.
 */
export function enrichAggregateWithLineage(input: LineageEnrichmentInput): FormulaAggregateResult {
  const { aggregate, linkage, linkageFailed } = input
  const descriptors = aggregate.descriptors.map((d) => {
    const hit = linkage[d.formulaId]
    if (!hit) return d
    return {
      ...d,
      lineage: {
        upstream: hit.upstream,
        downstream: hit.downstream,
        stale: Boolean(hit.stale),
      },
      valueStatus: hit.stale ? 'stale' : d.valueStatus,
    }
  })
  let status = aggregate.status
  if (linkageFailed && status === 'complete') status = 'partial'
  return { ...aggregate, status, descriptors }
}

/** Truth-source matrix rows used by guards. */
export const FORMULA_TRUTH_SOURCE_MATRIX = [
  {
    providerId: 'platform',
    origin: 'platform' as const,
    ruleKinds: ['data_fetch', 'calculation', 'presentation'] as FormulaRuleKind[],
    engine: 'backend_formula' as const,
    protection: 'protected' as const,
  },
  {
    providerId: 'user',
    origin: 'user' as const,
    ruleKinds: ['data_fetch', 'calculation'] as FormulaRuleKind[],
    engine: 'user_formula_store' as const,
    protection: 'editable' as const,
  },
  {
    providerId: 'auto_data',
    origin: 'runtime_generated' as const,
    ruleKinds: ['data_fetch'] as FormulaRuleKind[],
    engine: 'auto_data_resolver' as const,
    protection: 'system_managed' as const,
  },
  {
    providerId: 'logic_reasonableness',
    origin: 'platform' as const,
    ruleKinds: ['logic_check', 'reasonableness'] as FormulaRuleKind[],
    engine: 'backend_formula' as const,
    protection: 'protected' as const,
  },
  {
    providerId: 'frontend_engine',
    origin: 'platform' as const,
    ruleKinds: ['calculation', 'presentation'] as FormulaRuleKind[],
    engine: 'frontend_formula_engine' as const,
    protection: 'protected' as const,
  },
] as const
