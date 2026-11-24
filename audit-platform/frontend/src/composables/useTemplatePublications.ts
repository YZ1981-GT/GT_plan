/**
 * 自定义模板 publication 管理（list / commit-visibility / instantiate）。
 *
 * Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16 / 20
 *
 * 后端已就绪的三个端点：
 *   GET  /api/custom-template-ingestion/publications
 *   POST /api/custom-template-ingestion/publications/commit-visibility
 *   POST /api/custom-template-ingestion/publications/instantiate
 *
 * 🔴 本 composable 只做「展示 + 触发」，不伪造状态：
 *   - `runtimeDiscoverable` 一律取服务端返回值，前端不按 state 自己推；
 *   - instantiate 成功后必须真拿到 `workbookInstanceId` 才算成功，
 *     服务端返回 `instantiated: false` 时按失败处理（而不是当成功）。
 */
import { computed, ref, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

const BASE = '/api/custom-template-ingestion'

export interface TemplatePublication {
  publicationKey: string
  candidateId: string
  state: string
  artifactDigest: string
  authorityRef: string
  reason: string | null
  runtimeDiscoverable: boolean
  createdAt: string
  updatedAt: string
}

export interface CommitVisibilityResult {
  publicationKey: string
  visibilityState: string
  state: string
  runtimeDiscoverable: boolean
  requiredConsumers?: string[]
  idempotent: boolean
}

export interface InstantiateEntry {
  entryId: string
  sheetUid: string
  wpCode: string
  componentType: string
  projectionMode: string
}

export interface InstantiateResult {
  publicationKey: string
  workbookInstanceId: string
  projectId: string
  pinned: boolean
  instantiated: boolean
  sheetCount: number
  entries: InstantiateEntry[]
  contextFingerprint?: string
  workbookGeneration?: number
}

export interface SheetMappingInput {
  sheetUid: string
  wpCode: string
  componentType: string
  projectionMode: string
  sheetCode?: string | null
  manifestVersion?: string | null
}

export interface WithdrawResult {
  publicationKey: string
  state: string
  reason: string
  runtimeDiscoverable: boolean
}

export interface SecurityRevokeResult {
  publicationKey: string
  state: string
  reason: string
  affectedProjects: string[]
  pinsCleared: boolean
  runtimeDiscoverable: boolean
}

export interface UpgradeOffer {
  fromPublicationKey: string
  toPublicationKey: string
  diffDigest: string
  requiresApproval: boolean
}

export interface ApplyUpgradeResult {
  projectId: string
  pinnedTo: string
  stagingOk: boolean
}

/** preflight 报告里的单个 sheet（来自 `GET /artifacts/{id}` 的 manifest.preflight）。 */
export interface PreflightSheet {
  sheetUid: string
  sheetName: string
  order: number
  state: string
  /** 服务端推荐 mode，可作为前端默认值；用户仍可改。 */
  projectionRecommendation?: string
}

/** `projection_recommendation` → 我们的 `ProjectionMode` 取值。 */
export function toProjectionMode(recommendation: string | undefined): string {
  // 后端 ProjectionMode = editable_grid / read_only_html / onlyoffice_only
  // preflight 的 projectionRecommendation 是 ProjectionRecommendation 枚举，
  // 这里做保守映射：不认识的一律 editable_grid（可编辑网格最通用）。
  switch ((recommendation || '').toLowerCase()) {
    case 'read_only_html':
    case 'readonly_html':
      return 'read_only_html'
    case 'onlyoffice_only':
    case 'onlyoffice':
      return 'onlyoffice_only'
    default:
      return 'editable_grid'
  }
}

/** 后端必需 consumer（与 finalize_saga.REQUIRED_FINALIZE_CONSUMERS 逐值一致）。 */
export const REQUIRED_FINALIZE_CONSUMERS = [
  'guidance',
  'renderer',
  'public_shell',
  'entry_namespace',
] as const

export const PUBLICATION_STATE_LABELS: Record<string, string> = {
  PENDING_VISIBILITY: '待确认可见性',
  ACTIVE: '已发布（可实例化）',
  WITHDRAWN: '已撤回',
  SECURITY_REVOKED: '安全撤销',
  FAILED: '已失败',
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

export function useTemplatePublications() {
  const publications: Ref<TemplatePublication[]> = ref([])
  const loading = ref(false)
  const lastError = ref<string | null>(null)

  const pending = computed(() =>
    publications.value.filter((p) => p.state === 'PENDING_VISIBILITY'),
  )
  const active = computed(() =>
    publications.value.filter((p) => p.state === 'ACTIVE'),
  )

  async function load(state?: string): Promise<void> {
    loading.value = true
    lastError.value = null
    try {
      const response = await api.get<{ publications: TemplatePublication[] }>(
        `${BASE}/publications`,
        { params: state ? { state } : undefined, _silent: true },
      )
      publications.value = response?.publications ?? []
    } catch (error) {
      lastError.value = apiErrorMessage(error, '加载 publication 列表失败')
      publications.value = []
    } finally {
      loading.value = false
    }
  }

  /** 提交 ACK 并推进可见性。只有四个 consumer 全 ACCEPTED 才会 ACTIVE。 */
  async function commitVisibility(
    publicationKey: string,
    acks: { consumer: string; verdict: 'ACCEPTED' | 'REJECTED'; reasonCodes?: string[] }[],
  ): Promise<CommitVisibilityResult | null> {
    lastError.value = null
    try {
      const response = await api.post<CommitVisibilityResult>(
        `${BASE}/publications/commit-visibility`,
        {
          publicationKey,
          acks: acks.map((a) => ({
            consumer: a.consumer,
            consumerVersion: '1.0.0',
            verdict: a.verdict,
            reasonCodes: a.reasonCodes ?? [],
          })),
        },
        { _silent: true } as any,
      )
      await load()
      return response
    } catch (error) {
      lastError.value = apiErrorMessage(error, '推进可见性失败')
      return null
    }
  }

  /** 一键把四个 consumer 全标 ACCEPTED（仅用于演示 / 内部验收，真实场景应逐个收集）。 */
  async function acceptAllConsumers(publicationKey: string): Promise<CommitVisibilityResult | null> {
    return commitVisibility(
      publicationKey,
      REQUIRED_FINALIZE_CONSUMERS.map((c) => ({ consumer: c, verdict: 'ACCEPTED' as const })),
    )
  }

  /** 拉取该 artifact 的 preflight sheet 候选列表（供实例化弹窗做下拉）。 */
  async function loadPreflightSheets(artifactId: string): Promise<PreflightSheet[]> {
    lastError.value = null
    try {
      const response = await api.get<{ artifact: Record<string, unknown> }>(
        `${BASE}/artifacts/${artifactId}`,
        { _silent: true } as any,
      )
      const artifact = response?.artifact ?? {}
      const preflight = artifact.preflight as Record<string, unknown> | undefined
      const workbook = preflight?.workbook as Record<string, unknown> | undefined
      const raw = workbook?.sheets
      if (!Array.isArray(raw)) {
        lastError.value = '该产物没有 preflight sheet 报告，请先跑预检'
        return []
      }
      return raw
        .filter((s): s is Record<string, unknown> => !!s && typeof s === 'object')
        .map((s) => ({
          sheetUid: String(s.sheetUid ?? s.sheet_uid ?? ''),
          sheetName: String(s.sheetName ?? s.sheet_name ?? ''),
          order: Number(s.order ?? 0),
          state: String(s.state ?? ''),
          projectionRecommendation: s.projectionRecommendation
            ? String(s.projectionRecommendation)
            : undefined,
        }))
        .filter((s) => s.sheetUid)
        .sort((a, b) => a.order - b.order)
    } catch (error) {
      lastError.value = apiErrorMessage(error, '加载 preflight sheet 列表失败')
      return []
    }
  }

  /** 实例化：需要调用方给出 sheet 映射（服务端按 preflight 报告校验白名单）。 */
  async function instantiate(
    publicationKey: string,
    workingPaperId: string,
    sheets: SheetMappingInput[],
  ): Promise<InstantiateResult | null> {
    lastError.value = null
    if (!sheets.length) {
      lastError.value = '至少需要一个 sheet 映射'
      return null
    }
    try {
      const response = await api.post<InstantiateResult>(
        `${BASE}/publications/instantiate`,
        { publicationKey, workingPaperId, sheets },
        { _silent: true } as any,
      )
      // 🔴 服务端说没真实例化就不是成功 —— 不能把 pinned 当完成。
      if (!response?.instantiated || !response?.workbookInstanceId) {
        lastError.value = response?.instantiated === false
          ? '服务端未完成实例化（pinned 不等于已建册）'
          : '实例化回执缺少 workbookInstanceId'
        return null
      }
      await load()
      return response
    } catch (error) {
      lastError.value = apiErrorMessage(error, '实例化失败')
      return null
    }
  }

  // -------------------------------------------------------------------------
  // 撤回 / 安全撤销 / 升级（2026-11-24 接线：后端四端点此前无前端入口）
  // -------------------------------------------------------------------------

  /** 撤回 publication（ACTIVE → WITHDRAWN）。已 pin 的项目继续使用。 */
  async function withdraw(
    publicationKey: string,
    reason: string,
  ): Promise<WithdrawResult | null> {
    lastError.value = null
    if (!reason.trim()) {
      // 撤回必须写原因（与后端 Field(min_length=2) 同口径，前端先挡一次）。
      lastError.value = '撤回必须填写原因'
      return null
    }
    try {
      const response = await api.post<WithdrawResult>(
        `${BASE}/publications/${encodeURIComponent(publicationKey)}/withdraw`,
        { reason },
        { _silent: true } as any,
      )
      await load()
      return response
    } catch (error) {
      lastError.value = apiErrorMessage(error, '撤回失败')
      return null
    }
  }

  /** 安全撤销（ACTIVE → SECURITY_REVOKED）。默认清 pin，阻断后续实例化。 */
  async function securityRevoke(
    publicationKey: string,
    reason: string,
    clearPins = true,
  ): Promise<SecurityRevokeResult | null> {
    lastError.value = null
    if (!reason.trim()) {
      lastError.value = '安全撤销必须填写原因'
      return null
    }
    try {
      const response = await api.post<SecurityRevokeResult>(
        `${BASE}/publications/${encodeURIComponent(publicationKey)}/security-revoke`,
        { reason, clearPins },
        { _silent: true } as any,
      )
      await load()
      return response
    } catch (error) {
      lastError.value = apiErrorMessage(error, '安全撤销失败')
      return null
    }
  }

  /** 产出升级提议（不改状态）。项目必须已 pin，目标必须 ACTIVE。 */
  async function offerUpgrade(
    projectId: string,
    toPublicationKey: string,
  ): Promise<UpgradeOffer | null> {
    lastError.value = null
    try {
      return await api.post<UpgradeOffer>(
        `${BASE}/publications/upgrade-offer`,
        { projectId, toPublicationKey },
        { _silent: true } as any,
      )
    } catch (error) {
      lastError.value = apiErrorMessage(error, '生成升级提议失败')
      return null
    }
  }

  /** 执行升级（需要 ApprovalIntent）。stagingOk=false 时 pin 不变。 */
  async function applyUpgrade(
    projectId: string,
    toPublicationKey: string,
    approvalIntentId: string,
    stagingOk = true,
  ): Promise<ApplyUpgradeResult | null> {
    lastError.value = null
    if (!approvalIntentId.trim()) {
      lastError.value = '升级需要审批单号（ApprovalIntent）'
      return null
    }
    try {
      const response = await api.post<ApplyUpgradeResult>(
        `${BASE}/publications/apply-upgrade`,
        { projectId, toPublicationKey, approvalIntentId, stagingOk },
        { _silent: true } as any,
      )
      // 🔴 stagingOk=false 时服务端保持原 pin —— 不能当升级成功展示。
      if (!stagingOk) {
        lastError.value = 'staging 未就绪，项目仍使用原 publication'
      }
      await load()
      return response
    } catch (error) {
      lastError.value = apiErrorMessage(error, '执行升级失败')
      return null
    }
  }

  return {
    publications,
    pending,
    active,
    loading,
    lastError,
    load,
    commitVisibility,
    acceptAllConsumers,
    loadPreflightSheets,
    instantiate,
    withdraw,
    securityRevoke,
    offerUpgrade,
    applyUpgrade,
  }
}
