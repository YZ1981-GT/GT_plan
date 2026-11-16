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
import { api } from '@/services/apiProxy'
import {
  assertFShellConsumerCompatible,
  FSHELL_CONTRACT_VERSION,
  FSHELL_NON_CAPABILITIES,
} from '@/shell/formula/fShellContract'

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
  preflightDigest: string | null
  authorityId: string | null
  handoffId: string | null
  handoffDigest: string | null
  lastError: string | null
}

export interface UnitAuthorityInput {
  workingPaperId: string
  workbookSha256: string
  preflightDigest: string
  manifest: Record<string, unknown>
  manifestDigest: string
}

export interface FinalizeAuthorityInput {
  workingPaperId: string
  authorityId: string
  manifestDigest: string
  idempotencyKey: string
}

interface IngestResponse {
  artifactId: string
  state: string
  displayName: string
  sizeBytes: number
  sha256: string
  policyVersion: string
  actionId: string
  message: string
}

interface PreflightResponse {
  artifactId: string
  state: string
  preflight: Record<string, unknown>
  preflightDigest: string
}

interface AuthorityResponse {
  authorityId: string
  workingPaperId: string
  workbookSha256: string
  manifestDigest: string
  idempotent: boolean
}

interface FinalizeResponse {
  artifactId: string
  phase: 'finalized'
  handoffId: string
  handoffDigest: string
  idempotent: boolean
  runtimeDiscoverable: false
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return fallback
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
    preflightDigest: null,
    authorityId: null,
    handoffId: null,
    handoffDigest: null,
    lastError: null,
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

  const BASE = '/api/custom-template-ingestion'

  /** 上传字节到隔离区；返回 artifactId 与 sha256，绝不标记 ACTIVE。 */
  async function ingestFile(file: File): Promise<IngestResponse | null> {
    if (!fshell.ok) return null
    const form = new FormData()
    form.append('file', file)
    try {
      const response = await api.post<IngestResponse>(`${BASE}/ingest`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      })
      state.value = {
        ...state.value,
        entry: 'ingest_excel',
        artifactId: response.artifactId,
        phase: 'quarantined',
        staticPreviewOnly: true,
        hostFactsRegistered: false,
        preflightDigest: null,
        authorityId: null,
        handoffId: null,
        handoffDigest: null,
        lastError: null,
      }
      return response
    } catch (error) {
      setBlockers([
        {
          code: 'ingest_failed',
          messageZh: apiErrorMessage(error, '上传失败，请重试'),
          recoverable: true,
        },
      ])
      state.value = { ...state.value, lastError: apiErrorMessage(error, '上传失败，请重试') }
      return null
    }
  }

  /** 触发服务端 preflight，冻结 preflightDigest；失败即阻断，不伪造通过。 */
  async function runPreflight(artifactId?: string): Promise<PreflightResponse | null> {
    const id = artifactId ?? state.value.artifactId
    if (!fshell.ok || !id) return null
    try {
      const response = await api.post<PreflightResponse>(`${BASE}/artifacts/${id}/preflight`, undefined, {
        _silent: true,
      })
      state.value = {
        ...state.value,
        artifactId: id,
        phase: response.state === 'PREFLIGHT_READY' ? 'preflight' : 'blocked',
        preflightDigest: response.preflightDigest,
        lastError: null,
      }
      if (response.state !== 'PREFLIGHT_READY') {
        setBlockers([
          {
            code: 'preflight_failed',
            messageZh: '预检未通过：请按报告修正后重新上传',
            recoverable: true,
          },
        ])
      }
      return response
    } catch (error) {
      const message = apiErrorMessage(error, '预检失败，请重试')
      setBlockers([{ code: 'preflight_failed', messageZh: message, recoverable: true }])
      state.value = { ...state.value, lastError: message }
      return null
    }
  }

  /** 提交 unit authority；只在 preflightDigest 已冻结时可用。 */
  async function putUnitAuthority(
    input: UnitAuthorityInput,
    artifactId?: string,
  ): Promise<AuthorityResponse | null> {
    const id = artifactId ?? state.value.artifactId
    if (!fshell.ok || !id) return null
    if (!state.value.preflightDigest || state.value.preflightDigest !== input.preflightDigest) {
      setBlockers([
        {
          code: 'preflight_digest_mismatch',
          messageZh: '预检结果已变化，请重新预检后再确认单位',
          recoverable: true,
        },
      ])
      return null
    }
    try {
      const response = await api.put<AuthorityResponse>(
        `${BASE}/artifacts/${id}/unit-authority`,
        input,
        { _silent: true },
      )
      state.value = {
        ...state.value,
        authorityId: response.authorityId,
        phase: 'mapping',
        lastError: null,
      }
      return response
    } catch (error) {
      const message = apiErrorMessage(error, '单位确认失败，请重试')
      setBlockers([{ code: 'unit_authority_failed', messageZh: message, recoverable: true }])
      state.value = { ...state.value, lastError: message }
      return null
    }
  }

  /** finalize 只产出 handoff，不进入 ACTIVE。 */
  async function finalizeAuthority(
    input: FinalizeAuthorityInput,
    artifactId?: string,
  ): Promise<FinalizeResponse | null> {
    const id = artifactId ?? state.value.artifactId
    if (!fshell.ok || !id) return null
    // 🔴 防调用方拿过期 / 未确认的 authority 去定稿。这一条同时覆盖
    // 「本会话还没确认过单位」（state 为 null）与「传的是上一轮的 authority」
    // 两种情形，故不再单列 `!state.value.authorityId` —— 两处并存会互相兜底，
    // 把任何一处的变异掩盖掉（已实测）。
    if (input.authorityId !== state.value.authorityId) {
      setBlockers([
        {
          code: 'authority_id_mismatch',
          messageZh: '单位确认结果已变化，请重新确认后再定稿',
          recoverable: true,
        },
      ])
      return null
    }
    try {
      const response = await api.post<FinalizeResponse>(
        `${BASE}/artifacts/${id}/finalize`,
        input,
        { _silent: true },
      )
      state.value = {
        ...state.value,
        handoffId: response.handoffId,
        handoffDigest: response.handoffDigest,
        phase: 'pending_approval',
        hostFactsRegistered: false,
        staticPreviewOnly: true,
        lastError: null,
      }
      return response
    } catch (error) {
      const message = apiErrorMessage(error, '提交定稿失败，请重试')
      setBlockers([{ code: 'finalize_failed', messageZh: message, recoverable: true }])
      state.value = { ...state.value, lastError: message }
      return null
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
    ingestFile,
    runPreflight,
    putUnitAuthority,
    finalizeAuthority,
  }
}
