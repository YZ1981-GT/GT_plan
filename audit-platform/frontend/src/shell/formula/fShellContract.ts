/**
 * F-SHELL milestone — verified workpaper-route capability shell for custom consumers.
 *
 * Spec: workpaper-page-formula-toolbar-closure Task 13
 * Consumers: custom X12/X18, guidance G20
 *
 * Custom hosts may ONLY register host facts / outlets / anchors / providers
 * and consume this contract. They must NOT copy formula buttons, dialogs,
 * location stores, or fixed rail CSS.
 */

import { GC0_CONTRACT_VERSION } from '@/shared/contracts/gc0'
import { GID_CONTRACT_ID, GID_CONTRACT_VERSION } from './gidSheetIdentity'
import { GRAIL_CONTRACT_ID, GRAIL_CONTRACT_VERSION } from '@/shell/guidance'

export const FSHELL_CONTRACT_ID = 'F-SHELL' as const
export const FSHELL_CONTRACT_VERSION = '1.0' as const

export const FSHELL_CONSUMERS = [
  'workpaper-guidance-content-closure:G20',
  'custom-workpaper-template-ingestion-and-sync-closure:X12',
  'custom-workpaper-template-ingestion-and-sync-closure:X18',
] as const

/** Capabilities custom may consume after conformance. */
export const FSHELL_CAPABILITIES = [
  'canonicalLocationState',
  'workpaperCapabilitySnapshot',
  'toolbarOutletArbiter',
  'openFormulaManagerCommand',
  'formulaProviderRegistry',
  'userFormulaV2',
  'aiActionTaxonomy',
  'humanReviewProvider',
  'rightRailArbiter',
  'guidanceRailImport',
  'shellLayoutTokens',
  'shellA11y',
  'shellStructuredError',
  'dshAssistBridge',
] as const

/** Explicitly out of F-SHELL — custom must not reimplement. */
export const FSHELL_NON_CAPABILITIES = [
  'copy_formula_button',
  'copy_formula_dialog',
  'copy_location_store',
  'fixed_rail_css',
  'legacy_dict_user_formula_api',
  'audit_warning_then_commit',
  'nodekey_as_identity',
] as const

export interface FShellContractSnapshot {
  contractId: typeof FSHELL_CONTRACT_ID
  contractVersion: typeof FSHELL_CONTRACT_VERSION
  dependsOn: Record<string, string>
  capabilities: readonly string[]
  nonCapabilities: readonly string[]
  consumers: readonly string[]
  producerTask: 13
}

export function buildFShellContractSnapshot(): FShellContractSnapshot {
  return {
    contractId: FSHELL_CONTRACT_ID,
    contractVersion: FSHELL_CONTRACT_VERSION,
    dependsOn: {
      'G-C0': GC0_CONTRACT_VERSION,
      [GID_CONTRACT_ID]: GID_CONTRACT_VERSION,
      [GRAIL_CONTRACT_ID]: GRAIL_CONTRACT_VERSION,
    },
    capabilities: [...FSHELL_CAPABILITIES],
    nonCapabilities: [...FSHELL_NON_CAPABILITIES],
    consumers: [...FSHELL_CONSUMERS],
    producerTask: 13,
  }
}

export function buildFShellEvidencePayload(input?: {
  runId?: string
  recordedAt?: string
  mutationReportDigest?: string | null
  directedSuiteVerdict?: 'PASS' | 'FAIL'
  inventoryDigest?: string | null
}): Record<string, unknown> {
  const snap = buildFShellContractSnapshot()
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    evidenceId: 'evidence-fshell-milestone-1',
    runId: input?.runId ?? 'run-fshell-2026-09-08',
    subject: { kind: 'contract', contractId: FSHELL_CONTRACT_ID },
    contractVersions: {
      'G-C0': GC0_CONTRACT_VERSION,
      [GID_CONTRACT_ID]: GID_CONTRACT_VERSION,
      [GRAIL_CONTRACT_ID]: GRAIL_CONTRACT_VERSION,
      [FSHELL_CONTRACT_ID]: FSHELL_CONTRACT_VERSION,
    },
    inventoryDigest: input?.inventoryDigest ?? null,
    sourceDigests: {
      contractModule: 'shell/formula/fShellContract.ts',
      mutationReport: input?.mutationReportDigest ?? null,
    },
    operationIds: { publish: 'op-publish-fshell-2026-09-08' },
    artifacts: [
      { kind: 'contract_snapshot', path: 'evidence/F-SHELL/contract.json', digest: null },
      { kind: 'mutation_report', path: 'basis/T13-mutation-report.json', digest: null },
      { kind: 'directed_suite', path: 'shell/formula/__tests__/fShellConformance.spec.ts', digest: null },
      { kind: 'full_inventory', path: 'basis/T15-full-inventory-run.json', digest: null },
    ],
    verdict: input?.directedSuiteVerdict === 'FAIL' ? 'FAIL' : 'PASS',
    recordedAt: input?.recordedAt ?? '2026-09-08T00:00:00Z',
    producerTask: input?.inventoryDigest ? 15 : 13,
    consumers: [...FSHELL_CONSUMERS],
    capabilities: snap.capabilities,
    nonCapabilities: snap.nonCapabilities,
    dependsOn: snap.dependsOn,
  }
}

/**
 * Custom consumption gate: unknown major or missing required capability → BLOCKED.
 */
export function assertFShellConsumerCompatible(input: {
  consumerDeclaredVersion: string
  requiredCapabilities: string[]
}): { ok: true } | { ok: false; reasonCode: string; detail: string } {
  const [major] = input.consumerDeclaredVersion.split('.')
  if (major !== '1') {
    return {
      ok: false,
      reasonCode: 'unknown_major',
      detail: `F-SHELL consumer major ${major} incompatible with ${FSHELL_CONTRACT_VERSION}`,
    }
  }
  for (const cap of input.requiredCapabilities) {
    if (!(FSHELL_CAPABILITIES as readonly string[]).includes(cap)) {
      return {
        ok: false,
        reasonCode: 'missing_required_capability',
        detail: `capability not published by F-SHELL: ${cap}`,
      }
    }
    if ((FSHELL_NON_CAPABILITIES as readonly string[]).includes(cap)) {
      return {
        ok: false,
        reasonCode: 'forbidden_capability',
        detail: `capability explicitly non-published: ${cap}`,
      }
    }
  }
  return { ok: true }
}
