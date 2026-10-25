/**
 * Custom template ingestion wizard — F-SHELL consumer (Task 12).
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure
 * Requirements: 1.6, 2.6, 9.1, 9.3, 16.3
 *
 * Consumes F-SHELL via assertFShellConsumerCompatible. Does NOT copy formula
 * button/dialog/location store/fixed rail CSS.
 */
import { computed, ref, type Ref } from 'vue'
import {
  assertFShellConsumerCompatible,
  FSHELL_CONTRACT_VERSION,
  FSHELL_NON_CAPABILITIES,
} from '@/shell/formula'

export const CUSTOM_INGESTION_FSHELL_CONSUMER = 'custom-workpaper-template-ingestion-and-sync-closure:X12'

export const CUSTOM_INGESTION_REQUIRED_CAPABILITIES = [
  'canonicalLocationState',
  'workpaperCapabilitySnapshot',
  'toolbarOutletArbiter',
  'rightRailArbiter',
  'guidanceRailImport',
  'shellStructuredError',
] as const

export type IngestionEntryKind = 'batch_blank' | 'metadata_only' | 'ingest_excel'

export interface IngestionBlocker {
  code: string
  messageZh: string
  recoverable: boolean
}

export interface IngestionWizardState {
  entry: IngestionEntryKind | null
  artifactId: string | null
  phase:
    | 'idle'
    | 'quarantined'
    | 'preflight'
    | 'mapping'
    | 'candidate_preview'
    | 'pending_approval'
    | 'pending_visibility'
    | 'active'
    | 'blocked'
  blockers: IngestionBlocker[]
  staticPreviewOnly: boolean
  /** ACTIVE project entries only — never register on candidate upload success */
  hostFactsRegistered: boolean
}

export function gateFShellForCustomIngestion(): {
  ok: true
} | { ok: false; reasonCode: string; detail: string } {
  return assertFShellConsumerCompatible({
    consumerDeclaredVersion: FSHELL_CONTRACT_VERSION,
    requiredCapabilities: [...CUSTOM_INGESTION_REQUIRED_CAPABILITIES],
  })
}

export function assertNoForbiddenShellCopies(source: string): string[] {
  const hits: string[] = []
  for (const forbidden of FSHELL_NON_CAPABILITIES) {
    if (source.includes(forbidden)) hits.push(forbidden)
  }
  // Structural: literal copy markers
  for (const needle of [
    'copy_formula_button',
    'copy_formula_dialog',
    'copy_location_store',
    'fixed_rail_css',
  ]) {
    if (source.includes(needle) && !hits.includes(needle)) hits.push(needle)
  }
  return hits
}

export function entrySuccessMessage(kind: IngestionEntryKind): string {
  switch (kind) {
    case 'batch_blank':
      return '已创建空白批量底稿入口（尚未发布，不可实例化）'
    case 'metadata_only':
      return '已保存模板元数据（无文件字节，不可进入正式摄取）'
    case 'ingest_excel':
      return '文件已进入隔离区；上传成功 ≠ 发布 / 实例化'
  }
}

export function useCustomIngestionWizard() {
  const fshell = gateFShellForCustomIngestion()
  const state: Ref<IngestionWizardState> = ref({
    entry: null,
    artifactId: null,
    phase: fshell.ok ? 'idle' : 'blocked',
    blockers: fshell.ok
      ? []
      : [
          {
            code: fshell.reasonCode,
            messageZh: `F-SHELL 不兼容：${fshell.detail}`,
            recoverable: false,
          },
        ],
    staticPreviewOnly: true,
    hostFactsRegistered: false,
  })

  const canProceed = computed(
    () => fshell.ok && state.value.blockers.every((b) => b.recoverable || state.value.phase !== 'blocked'),
  )

  function selectEntry(kind: IngestionEntryKind) {
    if (!fshell.ok) return
    state.value = {
      ...state.value,
      entry: kind,
      phase: kind === 'ingest_excel' ? 'quarantined' : 'idle',
      staticPreviewOnly: true,
      // 上传/元数据成功绝不注册 host facts
      hostFactsRegistered: false,
    }
  }

  function setBlockers(blockers: IngestionBlocker[]) {
    state.value = {
      ...state.value,
      blockers,
      phase: blockers.some((b) => !b.recoverable) ? 'blocked' : state.value.phase,
    }
  }

  function markCandidatePreview() {
    state.value = {
      ...state.value,
      phase: 'candidate_preview',
      staticPreviewOnly: true,
      hostFactsRegistered: false,
    }
  }

  function markActiveAndRegisterHostFacts() {
    if (state.value.phase === 'blocked') {
      throw new Error('blocked publication cannot register host facts')
    }
    state.value = {
      ...state.value,
      phase: 'active',
      hostFactsRegistered: true,
      staticPreviewOnly: false,
    }
  }

  function revalidateCapabilities(allowed: boolean) {
    if (!allowed) {
      setBlockers([
        {
          code: 'capability_revoked',
          messageZh: '权限已变更：当前角色不可继续摄取，请刷新后重试',
          recoverable: true,
        },
      ])
      state.value = { ...state.value, hostFactsRegistered: false, phase: 'blocked' }
    }
  }

  return {
    fshell,
    state,
    canProceed,
    selectEntry,
    setBlockers,
    markCandidatePreview,
    markActiveAndRegisterHostFacts,
    revalidateCapabilities,
    entrySuccessMessage,
  }
}
