/**
 * workpaper-route red-baseline G-C0 consumption touchpoint.
 *
 * This module is the FIRST runtime consumer of G-C0 within the
 * workpaper-route scope. Its existence proves that this spec (F1:
 * `workpaper-page-formula-toolbar-closure`) actually imports the
 * three C0 top-level types it is required to use (Req 1.4 / 2.1)
 * and runs a fail-closed major-version gate at a real wiring point.
 *
 * What it does:
 * - Re-exports the three C0 types downstream spec consumers will use.
 * - `assertBaselineEnvelope`: the runtime touchpoint that runs
 *   `validateContractVersion` against an EvidenceEnvelope payload.
 *   It NEVER returns the payload — it returns a typed
 *   `BaselineWiringResult` — so a caller cannot accidentally skip
 *   the check by inspecting the raw envelope.
 *
 * What it does NOT do:
 * - It does NOT define a second `CanonicalWorkpaperLocation`,
 *   `EvidenceEnvelope` or `GuidanceRailAdapter` type. Those are
 *   imported. `discover_local_dupes` on the backend fails the
 *   conformance test if this module (or any other F1 module) re-declares
 *   any C0 top-level symbol.
 *
 * Mutation anchor M1 (self-check): the caller (test file) will mutate
 * `GC0_CONTRACT_VERSION` in `index.ts` to `'2.0'`, then assert that
 * `assertBaselineEnvelope` on the canonical evidence fixture returns
 * `outcome === 'BLOCKED'` (fail-closed). If the wiring ever drops
 * the validator call, that mutation goes GREEN, which the guard
 * must surface as ANCHOR-MISS.
 */

import {
  GC0_CONTRACT_ID,
  GC0_CONTRACT_VERSION,
  validateContractVersion,
  type CanonicalWorkpaperLocation,
  type EvidenceEnvelope,
  type GuidanceRailAdapter,
} from './index'

export {
  CanonicalWorkpaperLocation,
  EvidenceEnvelope,
  GuidanceRailAdapter,
  GC0_CONTRACT_ID,
  GC0_CONTRACT_VERSION,
}

export type BaselineWiringVerdict = 'ACCEPT' | 'BLOCKED' | 'DEGRADED' | 'REJECTED'

export interface BaselineWiringResult {
  verdict: BaselineWiringVerdict
  negotiatedVersion: string | null
  contractId: string
  contractVersion: string
  reasonCodes: string[]
}

/**
 * The runtime consumer-side wiring gate for workpaper route capability
 * payloads. This is the fail-closed major-version touchpoint required
 * by Requirement 1.4 ("consume G-C0") and Requirement 2.1
 * ("consume CanonicalWorkpaperLocation / EvidenceEnvelope /
 * GuidanceRailAdapter ... do not declare a local interface").
 *
 * Never returns the input payload. Callers get a typed verdict and
 * reason codes so the wiring is unambiguous.
 */
export function assertBaselineEnvelope(
  envelope: EvidenceEnvelope,
): BaselineWiringResult {
  const decision = validateContractVersion(envelope)
  return {
    verdict: decision.outcome,
    negotiatedVersion: decision.negotiatedVersion,
    contractId: GC0_CONTRACT_ID,
    contractVersion: GC0_CONTRACT_VERSION,
    reasonCodes: decision.reasons.map((r) => r.code),
  }
}

/**
 * Convenience helper for the location state provider: given a
 * CanonicalWorkpaperLocation, produce the identity tuple required by
 * Requirement 2.2 to distinguish "uninitialized / blocked / ready".
 *
 * Returns null when the location fails the G-C0 major-version gate —
 * the caller must treat that as BLOCKED and MUST NOT construct a
 * `ready` snapshot from a stale identity.
 */
export function assertLocationIdentity(
  location: CanonicalWorkpaperLocation,
): {
  wpId: string
  wpCode: string
  host: CanonicalWorkpaperLocation['host']
  anchorKind: CanonicalWorkpaperLocation['anchor']['kind']
  ownerEpoch: number
  contextRevision: number
} | null {
  const decision = validateContractVersion(location)
  if (decision.outcome !== 'ACCEPT') return null
  return {
    wpId: location.wpId,
    wpCode: location.wpCode,
    host: location.host,
    anchorKind: location.anchor.kind,
    ownerEpoch: location.ownerEpoch,
    contextRevision: location.contextRevision,
  }
}

/**
 * Rail adapter is not consumed by this module beyond import; the
 * function below exists so the C0 rail adapter identity is exercised
 * at the version gate without duplicating the type locally.
 *
 * Returns null when the adapter version fails the gate — the shell
 * MUST treat that as a blocked rail and not render a rail from a
 * stale identity.
 */
export function assertRailIdentity(
  adapter: GuidanceRailAdapter,
): {
  id: 'guidance'
  visible: boolean
  disabledReason: string | null
  hasDraft: boolean
} | null {
  const decision = validateContractVersion(adapter)
  if (decision.outcome !== 'ACCEPT') return null
  return {
    id: adapter.id,
    visible: adapter.visible,
    disabledReason: adapter.disabledReason,
    hasDraft: adapter.hasDraft,
  }
}
