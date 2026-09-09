/**
 * Formula-toolbar Task 7 — provider registry + aggregate + lineage.
 */

import { describe, expect, it } from 'vitest'

import { GC0_CONTRACT_VERSION, type CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import {
  FORMULA_TRUTH_SOURCE_MATRIX,
  FormulaProviderRegistry,
  aggregateProviderResults,
  createDefaultFormulaProviderRegistry,
  enrichAggregateWithLineage,
  semanticDigestOf,
  type FormulaDescriptor,
  type FormulaProviderAdapter,
  type FormulaProviderResult,
} from '@/shell/formula/formulaProviderRegistry'

function loc(): CanonicalWorkpaperLocation {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: 'org',
    projectId: 'p1',
    fiscalYear: 2026,
    wpId: 'wp-1',
    wpCode: 'D0',
    entryId: null,
    host: 'html',
    anchor: { kind: 'sheet', sheetUid: 's1', sheetCode: 'D0-1' },
    display: { sheetName: '明细', sectionLabel: null },
    ownerEpoch: 1,
    contextRevision: 1,
  }
}

function descriptor(
  formulaId: string,
  digest: string,
  providerId: string,
): FormulaDescriptor {
  return {
    descriptorVersion: '2.0',
    formulaId,
    semanticDigest: digest,
    origin: 'platform',
    ruleKind: 'data_fetch',
    engine: 'backend_formula',
    protection: 'protected',
    location: loc(),
    target: { addrId: null, fieldKey: null, rowKey: null, columnKey: null, a1: 'A1' },
    formulaFunction: 'SUM',
    ruleCategory: 'auto_calc',
    expression: '=1',
    ruleSummary: 'test',
    refs: [],
    currentValue: 1,
    valueStatus: 'resolved',
    calculatedAt: null,
    contextFingerprint: 'fp',
    manualOverride: false,
    version: '1',
    owner: providerId,
    protectionReason: null,
    updatedBy: null,
    updatedAt: null,
    provenance: { providerId, sourceDigest: digest },
  }
}

describe('Task 7: FormulaProviderRegistry', () => {
  it('registers five truth-source adapters matching the matrix', () => {
    const reg = createDefaultFormulaProviderRegistry()
    expect(reg.listProviderIds()).toEqual(
      [...FORMULA_TRUTH_SOURCE_MATRIX.map((m) => m.providerId)].sort(),
    )
    for (const row of FORMULA_TRUTH_SOURCE_MATRIX) {
      expect(reg.listProviderIds()).toContain(row.providerId)
    }
  })

  it('rejects duplicate provider registration', () => {
    const reg = new FormulaProviderRegistry()
    const a: FormulaProviderAdapter = {
      providerId: 'platform',
      supports: () => true,
      query: () => ({ providerId: 'platform', verdict: 'ok', reason: null, descriptors: [] }),
    }
    reg.register(a)
    expect(() => reg.register(a)).toThrow(/duplicate/)
  })

  it('same id+digest merges; different digest → collision blocked', () => {
    const location = loc()
    const same: FormulaProviderResult[] = [
      {
        providerId: 'platform',
        verdict: 'ok',
        reason: null,
        descriptors: [descriptor('f1', 'd1', 'platform')],
      },
      {
        providerId: 'user',
        verdict: 'ok',
        reason: null,
        descriptors: [descriptor('f1', 'd1', 'user')],
      },
    ]
    const merged = aggregateProviderResults(location, same)
    expect(merged.collisions).toHaveLength(0)
    expect(merged.descriptors).toHaveLength(1)
    expect(merged.status).toBe('complete')

    const clash: FormulaProviderResult[] = [
      {
        providerId: 'platform',
        verdict: 'ok',
        reason: null,
        descriptors: [descriptor('f1', 'digest-a', 'platform')],
      },
      {
        providerId: 'user',
        verdict: 'ok',
        reason: null,
        descriptors: [descriptor('f1', 'digest-b', 'user')],
      },
    ]
    const blocked = aggregateProviderResults(location, clash)
    expect(blocked.status).toBe('blocked')
    expect(blocked.collisions).toHaveLength(1)
    expect(blocked.descriptors).toHaveLength(0)
  })

  it('provider error/timeout → partial; lineage failure keeps descriptors', () => {
    const location = loc()
    const results: FormulaProviderResult[] = [
      {
        providerId: 'platform',
        verdict: 'ok',
        reason: null,
        descriptors: [descriptor('f1', 'd1', 'platform')],
      },
      {
        providerId: 'user',
        verdict: 'timeout',
        reason: 'timeout',
        descriptors: [],
      },
    ]
    const agg = aggregateProviderResults(location, results)
    expect(agg.status).toBe('partial')
    expect(agg.descriptors).toHaveLength(1)

    const enriched = enrichAggregateWithLineage({
      aggregate: agg,
      linkage: { f1: { upstream: ['u1'], downstream: ['d1'], stale: true } },
      linkageFailed: true,
    })
    expect(enriched.status).toBe('partial')
    expect(enriched.descriptors[0].lineage?.upstream).toEqual(['u1'])
    expect(enriched.descriptors[0].valueStatus).toBe('stale')
  })

  it('formulaFunction and ruleCategory stay separate fields', () => {
    const d = descriptor('f2', semanticDigestOf({ a: 1 }), 'platform')
    expect(d.formulaFunction).toBe('SUM')
    expect(d.ruleCategory).toBe('auto_calc')
    expect(d.formulaFunction).not.toBe(d.ruleCategory)
  })
})
