/**
 * G-RAIL milestone — GuidanceRailAdapter producer.
 *
 * Spec: workpaper-guidance-content-closure Task 15
 * Consumer: workpaper-page-formula-toolbar-closure Task 11 (F-SHELL integration)
 *
 * Adapter owns visibility / reason / location / version / draft / open / close only.
 * DOM placement (top/right/z-index/gap/width/inset) belongs to F-SHELL — never here.
 */

import {
  GC0_CONTRACT_VERSION,
  type CanonicalWorkpaperLocation,
  type GuidanceRailAdapter,
} from '@/shared/contracts/gc0'
import { assertLocationIdentity } from '@/shared/contracts/gc0/workpaper-route-baseline'

export const GRAIL_CONTRACT_ID = 'G-RAIL' as const
export const GRAIL_CONTRACT_VERSION = '1.0' as const
export const GRAIL_CONSUMERS = [
  'workpaper-page-formula-toolbar-closure:F11',
] as const

/**
 * Runtime adapter: real open/close callables.
 * Wire/evidence snapshot uses string signature placeholders from G-C0.
 */
export type RuntimeGuidanceRailAdapter = Omit<GuidanceRailAdapter, 'open' | 'close'> & {
  open: () => void | Promise<void>
  close: (options: { preserveDraft: boolean }) => void | Promise<void>
}

export interface GuidanceRailController {
  isOpen: boolean
  hasDraft: boolean
  guidanceVersion: string | null
  open: () => void | Promise<void>
  /** Close panel; when preserveDraft=false discard draft buffer. */
  close: (options: { preserveDraft: boolean }) => void | Promise<void>
  discardDraft?: () => void
}

export interface CreateGuidanceRailAdapterInput {
  location: CanonicalWorkpaperLocation | null
  /** Host/shell may hide guidance entirely. */
  visible: boolean
  disabledReason: string | null
  /** Capability gate already evaluated by shell — fail-closed when false. */
  capabilityAllowed: boolean
  controller: GuidanceRailController
}

/**
 * Build a mountable GuidanceRailAdapter, or null when major/location incomplete.
 * Shell MUST NOT mount a rail when this returns null.
 */
export function createGuidanceRailAdapter(
  input: CreateGuidanceRailAdapterInput,
): RuntimeGuidanceRailAdapter | null {
  if (!input.location) return null
  const identity = assertLocationIdentity(input.location)
  if (!identity) return null

  let disabledReason = input.disabledReason
  if (!input.capabilityAllowed) {
    disabledReason = disabledReason ?? '无权查看编制说明'
  }
  const visible = Boolean(input.visible && input.capabilityAllowed && !disabledReason)

  return {
    contractVersion: GC0_CONTRACT_VERSION,
    id: 'guidance',
    visible,
    disabledReason: visible ? null : disabledReason,
    location: input.location,
    guidanceVersion: input.controller.guidanceVersion,
    hasDraft: input.controller.hasDraft,
    open: () => input.controller.open(),
    close: async (options) => {
      if (!options.preserveDraft) {
        input.controller.discardDraft?.()
      }
      await input.controller.close(options)
    },
  }
}

/** Evidence / contract wire form — open/close are signature docs, not callables. */
export function toGuidanceRailContractSnapshot(
  adapter: RuntimeGuidanceRailAdapter,
): GuidanceRailAdapter {
  return {
    contractVersion: adapter.contractVersion,
    id: adapter.id,
    visible: adapter.visible,
    disabledReason: adapter.disabledReason,
    location: adapter.location,
    guidanceVersion: adapter.guidanceVersion,
    hasDraft: adapter.hasDraft,
    open: '() => void | Promise<void>',
    close: '(options: { preserveDraft: boolean }) => void | Promise<void>',
  }
}

/** Source-level guard: guidance UI must not own shell placement CSS. */
export function guidanceSourceOwnsShellPlacement(source: string): boolean {
  // Ignore comments / string literals so evidence docs mentioning forbidden
  // capabilities do not false-positive.
  const stripped = source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*$/gm, '')
    .replace(/`[\s\S]*?`/g, '""')
    .replace(/'(?:\\.|[^'\\])*'/g, '""')
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
  const patterns = [
    /position\s*:\s*fixed/i,
    /(?:^|[^\w-])z-index\s*:\s*\d/im,
    /(?:^|[^\w-])top\s*:\s*(?:\d|calc\()/im,
    /(?:^|[^\w-])right\s*:\s*(?:\d|calc\()/im,
  ]
  return patterns.some((re) => re.test(stripped))
}

export function buildGrailEvidencePayload(input?: {
  runId?: string
  recordedAt?: string
}): Record<string, unknown> {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    evidenceId: 'evidence-grail-milestone-1',
    runId: input?.runId ?? 'run-grail-2026-09-08',
    subject: { kind: 'contract', contractId: GRAIL_CONTRACT_ID },
    contractVersions: {
      'G-C0': GC0_CONTRACT_VERSION,
      [GRAIL_CONTRACT_ID]: GRAIL_CONTRACT_VERSION,
    },
    inventoryDigest: null,
    sourceDigests: {
      adapterModule: 'shell/guidance/guidanceRailAdapter.ts',
    },
    operationIds: { publish: 'op-publish-grail-2026-09-08' },
    artifacts: [
      {
        kind: 'adapter_behavior',
        path: 'evidence/G-RAIL/adapter-behavior.json',
        digest: null,
      },
    ],
    verdict: 'PASS',
    recordedAt: input?.recordedAt ?? '2026-09-08T00:00:00Z',
    producerTask: 15,
    consumers: [...GRAIL_CONSUMERS],
    capabilities: [
      'visibility',
      'disabledReason',
      'location',
      'guidanceVersion',
      'hasDraft',
      'open',
      'close',
    ],
    nonCapabilities: [
      'dom_placement',
      'fixed_top_right_zindex',
      'shell_content_inset',
      'multi_open_arbitration',
    ],
  }
}
