/**
 * Conformance spec for the workpaper-route G-C0 consumption touchpoint.
 *
 * This spec proves:
 *
 * 1. The three C0 top-level types required by Requirement 1.4 / 2.1
 *    (`CanonicalWorkpaperLocation`, `EvidenceEnvelope`, `GuidanceRailAdapter`)
 *    are imported — not re-declared — from `./index`.
 * 2. `assertBaselineEnvelope` runs `validateContractVersion` and returns a
 *    typed verdict (never the raw payload).
 * 3. The fail-closed major-version gate behaves as documented:
 *    a well-formed envelope ACCEPTs, an unknown-major envelope BLOCKs.
 * 4. The three runtime guards (`assertBaselineEnvelope`,
 *    `assertLocationIdentity`, `assertRailIdentity`) all agree on
 *    ACCEPT vs BLOCKED across a minimal fixture set.
 *
 * Mutation anchor M1: if this module ever stops calling
 * `validateContractVersion`, test_mutation_anchor_blocking_version_turns_red
 * will flip RED.
 */

import { describe, expect, it } from 'vitest'

import {
  GC0_CONTRACT_ID,
  GC0_CONTRACT_VERSION,
  type CanonicalWorkpaperLocation,
  type EvidenceEnvelope,
  type GuidanceRailAdapter,
} from './index'
import {
  assertBaselineEnvelope,
  assertLocationIdentity,
  assertRailIdentity,
} from './workpaper-route-baseline'


function makeEnvelope(): EvidenceEnvelope {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    evidenceId: 'ev-task1-1',
    runId: 'run-task1-1',
    subject: { kind: 'contract', contractId: GC0_CONTRACT_ID },
    contractVersions: { [GC0_CONTRACT_ID]: GC0_CONTRACT_VERSION },
    inventoryDigest: null,
    sourceDigests: {},
    operationIds: {},
    artifacts: [],
    verdict: 'PASS',
    recordedAt: '2026-09-07T00:00:00Z',
  }
}

function makeLocation(): CanonicalWorkpaperLocation {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: 'org-1',
    projectId: 'proj-1',
    fiscalYear: 2025,
    wpId: 'wp-1',
    wpCode: 'E1-1',
    entryId: 'e-1',
    host: 'html',
    anchor: { kind: 'cell', sheetUid: 's-1', addrId: null, rowKey: 'r', columnKey: 'c', a1: 'A1' },
    display: { sheetName: '货币资金', sectionLabel: null },
    ownerEpoch: 1,
    contextRevision: 1,
  }
}

function makeRail(): GuidanceRailAdapter {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    id: 'guidance',
    visible: true,
    disabledReason: null,
    location: makeLocation(),
    guidanceVersion: 'g-1',
    hasDraft: false,
    open: '() => void | Promise<void>',
    close: '(options: { preserveDraft: boolean }) => void | Promise<void>',
  }
}

describe('workpaper-route G-C0 consumption touchpoint (Task 1)', () => {
  it('re-exports the three required C0 types with matching identity', () => {
    // Proves:
    // - the module imports and re-exports `GC0_CONTRACT_ID` / `_VERSION`
    //   from `./index` (not a local re-declaration)
    // - downstream F1 modules can import these without duplicating the
    //   identity tuple (Req 2.1).
    expect(GC0_CONTRACT_ID).toBe('G-C0')
    expect(GC0_CONTRACT_VERSION).toBe('1.0')
    // The three types are type-only imports — cannot be asserted at
    // runtime. Their non-duplication is enforced by the backend
    // `discover_local_dupes` scanner in test_workpaper_route_task1_baseline.py.
    expect(typeof assertBaselineEnvelope).toBe('function')
    expect(typeof assertLocationIdentity).toBe('function')
    expect(typeof assertRailIdentity).toBe('function')
  })

  it('assertBaselineEnvelope ACCEPTs a well-formed envelope and returns a typed verdict', () => {
    const result = assertBaselineEnvelope(makeEnvelope())
    expect(result).toEqual({
      verdict: 'ACCEPT',
      negotiatedVersion: '1.0',
      contractId: 'G-C0',
      contractVersion: '1.0',
      reasonCodes: [],
    })
    // Never returns the raw envelope — no `evidenceId` on the result.
    expect('evidenceId' in result).toBe(false)
  })

  it('assertBaselineEnvelope BLOCKs an unknown-major version (fail-closed)', () => {
    const envelope = makeEnvelope()
    envelope.contractVersion = '2.0' as typeof GC0_CONTRACT_VERSION
    const result = assertBaselineEnvelope(envelope)
    expect(result.verdict).toBe('BLOCKED')
    expect(result.reasonCodes).toContain('unknown-major')
    expect(result.negotiatedVersion).toBeNull()
  })

  it('assertBaselineEnvelope BLOCKs a malformed version (fail-closed)', () => {
    const envelope = makeEnvelope()
    envelope.contractVersion = '1.x' as typeof GC0_CONTRACT_VERSION
    const result = assertBaselineEnvelope(envelope)
    expect(result.verdict).toBe('BLOCKED')
    expect(result.reasonCodes).toContain('identity-malformed')
  })

  it('assertBaselineEnvelope DEGRADES for an unsupported minor when consuming', () => {
    const envelope = makeEnvelope()
    envelope.contractVersion = '1.5' as typeof GC0_CONTRACT_VERSION
    const result = assertBaselineEnvelope(envelope)
    expect(result.verdict).toBe('DEGRADED')
    expect(result.negotiatedVersion).toBe('1.0')
  })

  it('assertLocationIdentity returns null on a BLOCKED version (Req 2.2 gate)', () => {
    const location = makeLocation()
    location.contractVersion = '9.0' as typeof GC0_CONTRACT_VERSION
    expect(assertLocationIdentity(location)).toBeNull()
  })

  it('assertLocationIdentity returns the identity tuple on a matching version', () => {
    const result = assertLocationIdentity(makeLocation())
    expect(result).not.toBeNull()
    expect(result!.wpId).toBe('wp-1')
    expect(result!.wpCode).toBe('E1-1')
    expect(result!.anchorKind).toBe('cell')
    expect(result!.ownerEpoch).toBe(1)
    expect(result!.contextRevision).toBe(1)
  })

  it('assertRailIdentity returns null on a BLOCKED version', () => {
    const rail = makeRail()
    rail.contractVersion = '9.0' as typeof GC0_CONTRACT_VERSION
    expect(assertRailIdentity(rail)).toBeNull()
  })

  it('assertRailIdentity returns the rail tuple on a matching version', () => {
    const result = assertRailIdentity(makeRail())
    expect(result).not.toBeNull()
    expect(result!.id).toBe('guidance')
    expect(result!.visible).toBe(true)
    expect(result!.disabledReason).toBeNull()
  })

  // ---------------------------------------------------------------------
  // Mutation anchor M1 — proves the version gate is wired.
  //
  // The parent backend test file mutates `GC0_CONTRACT_VERSION` in
  // `index.ts` to `'2.0'` and re-runs this module via subprocess.
  // If this module ever stops calling `validateContractVersion`, the
  // mutated constant will still produce ACCEPT from a plain object
  // without the gate — which the anchor asserts is NOT the case.
  //
  // Kept in this file so the vitest suite is the mutation target; the
  // backend test drives the mutation + asserts RED/GREEN classification.
  // ---------------------------------------------------------------------

  it('mutation anchor: envelope gate catches the version drift', () => {
    // Simulates the mutation without actually mutating the source file
    // (backend test does the on-disk mutation; this test exercises the
    // gate under the same condition locally).
    const envelope = makeEnvelope()
    envelope.contractVersion = '2.0' as typeof GC0_CONTRACT_VERSION
    expect(assertBaselineEnvelope(envelope).verdict).toBe('BLOCKED')
  })
})
