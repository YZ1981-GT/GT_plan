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
      } as any)
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
      } as any)
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

  /**
   * 拉取该 artifact 的逐 region 候选清单（来自 preflight 报告的
   * amountRegionCandidates；按 sheet 分组扁平返回）。空数组 = 报告里没有
   * 数值列候选 —— unit-authority 仍可提交（比如全是文本模板），但界面会提示。
   */
  async function loadRegionCandidates(artifactId?: string): Promise<PreflightRegionCandidate[]> {
    const id = artifactId ?? state.value.artifactId
    if (!fshell.ok || !id) return []
    try {
      const response = await api.get<{ artifact: Record<string, unknown> }>(
        `${BASE}/artifacts/${id}`,
        { _silent: true } as any,
      )
      const artifact = response?.artifact ?? {}
      const preflight = artifact.preflight as Record<string, unknown> | undefined
      const workbook = preflight?.workbook as Record<string, unknown> | undefined
      const raw = workbook?.sheets
      if (!Array.isArray(raw)) return []
      const out: PreflightRegionCandidate[] = []
      for (const s of raw) {
        if (!s || typeof s !== 'object') continue
        const sheetUid = String((s as Record<string, unknown>).sheetUid ?? '')
        const sheetName = String((s as Record<string, unknown>).sheetName ?? '')
        const cands = (s as Record<string, unknown>).amountRegionCandidates
        if (!Array.isArray(cands)) continue
        for (const c of cands) {
          if (!c || typeof c !== 'object') continue
          const r = c as Record<string, unknown>
          out.push({
            stableId: String(r.stableId ?? ''),
            columnLetter: String(r.columnLetter ?? ''),
            header: String(r.header ?? ''),
            numericCells: Number(r.numericCells ?? 0),
            firstNumericRow: Number(r.firstNumericRow ?? 0),
            sheetUid,
            sheetName,
          })
        }
      }
      return out.filter((c) => c.stableId)
    } catch (error) {
      setBlockers([{
        code: 'region_candidates_failed',
        messageZh: apiErrorMessage(error, '加载金额列候选失败'),
        recoverable: true,
      }])
      return []
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
        { _silent: true } as any,
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
        { _silent: true } as any,
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
    loadRegionCandidates,
    putUnitAuthority,
    finalizeAuthority,
  }
}


// ---------------------------------------------------------------------------
// 逐 amount region 确认（2026-11-24 平台技术债清偿）
//
// 背景：unit-authority 的 manifest.regions 此前只能由调用方手写 JSON，没有
// 「确认界面」。preflight 报告现在按列统计产出 amountRegionCandidates（后端
// semantic_preflight._amount_region_candidates），本段把它变成用户可裁决的清单：
//   loadRegionCandidates(artifactId) → PreflightRegionCandidate[]
//   buildRegionsFromDecisions(...)  → manifest.regions（形状与后端校验逐字段一致）
// scanner 只给候选（列位置 + 表头 + 数值格数），单位 / kind 语义由用户裁决 ——
// 不猜单位（与后端 _validate_authority_manifest 的允许集合同口径）。
// ---------------------------------------------------------------------------

/** preflight 报告里的单列金额 region 候选（camelCase，后端 to_dict 同形）。 */
export interface PreflightRegionCandidate {
  stableId: string
  columnLetter: string
  header: string
  numericCells: number
  firstNumericRow: number
  /** 候选所在 sheet（前端分组展示用；不进 manifest.regions）。 */
  sheetUid: string
  sheetName: string
}

/** 用户对一个 region 的裁决（决定 manifest.regions 成员形状）。 */
export interface RegionDecision {
  stableId: string
  measureKind: 'amount' | 'quantity' | 'count' | 'ratio' | 'exchange_rate' | 'unit_price' | 'text'
  /** amount 必填：yuan / qian / wan */
  unit?: 'yuan' | 'qian' | 'wan'
  /** amount 必填：与 unit 对应的除数（1 / 1000 / 10000） */
  divisor?: 1 | 1000 | 10000
  /** ratio 必填：fraction / percent_points；非 ratio 禁传 */
  ratioScale?: 'fraction' | 'percent_points'
}

/** 后端 ALLOWED 集合（与 custom_template_ingestion._validate_authority_manifest 同口径）。 */
export const REGION_ALLOWED_KINDS = [
  'amount', 'quantity', 'count', 'ratio', 'exchange_rate', 'unit_price', 'text',
] as const
export const REGION_ALLOWED_UNITS: Record<string, 1 | 1000 | 10000> = {
  yuan: 1,
  qian: 1000,
  wan: 10000,
}
export const REGION_ALLOWED_SCALES = ['fraction', 'percent_points'] as const

/** 后端 kind 命名是 snake_case（measure_kind），前端裁决用下划线形态直传。 */
export function toSnakeKind(kind: RegionDecision['measureKind']): string {
  return kind.replace(/_/g, '_')
}

/** 从裁决组装 manifest.regions；非法组合抛中文错误（不静默丢字段）。 */
export function buildRegionsFromDecisions(
  decisions: RegionDecision[],
): { regions: Record<string, unknown>[]; errors: string[] } {
  const errors: string[] = []
  const regions: Record<string, unknown>[] = []
  const seen = new Set<string>()
  for (const d of decisions) {
    if (seen.has(d.stableId)) {
      errors.push(`region ${d.stableId} 重复`)
      continue
    }
    seen.add(d.stableId)
    if (!(REGION_ALLOWED_KINDS as readonly string[]).includes(d.measureKind)) {
      errors.push(`region ${d.stableId} 的 measure_kind 无效：${d.measureKind}`)
      continue
    }
    const region: Record<string, unknown> = {
      stable_id: d.stableId,
      measure_kind: d.measureKind,
    }
    if (d.measureKind === 'ratio') {
      if (d.ratioScale && (REGION_ALLOWED_SCALES as readonly string[]).includes(d.ratioScale)) {
        region.ratio_scale = d.ratioScale
      } else {
        errors.push(`ratio region ${d.stableId} 必须声明 ratio_scale（fraction 或 percent_points）`)
        continue
      }
    } else if (d.ratioScale) {
      errors.push(`非 ratio region ${d.stableId} 不得声明 ratio_scale`)
      continue
    }
    if (d.measureKind === 'amount') {
      if (!d.unit || !(d.unit in REGION_ALLOWED_UNITS)) {
        errors.push(`amount region ${d.stableId} 必须选择单位（元/千元/万元）`)
        continue
      }
      region.unit = d.unit
      region.divisor = REGION_ALLOWED_UNITS[d.unit]
    }
    regions.push(region)
  }
  return { regions, errors }
}
