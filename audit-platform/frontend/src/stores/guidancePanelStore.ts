/**
 * 底稿编制指导面板 Store
 *
 * `setWpContext()` 是上下文变化时唯一的自动请求入口。缓存仅用于短时首屏预览，
 * 每次切换 context 仍会 revalidate 服务端版本；旧请求必须同时通过 request id 与
 * context identity 两道校验才能回写。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/services/apiProxy'

export type GuidanceHost = 'html' | 'univer' | 'onlyoffice'
export type GuidanceSource =
  | 'template_sheet'
  | 'template_header'
  | 'docx_instructions'
  | 'static_json'
  | 'typed_fallback'
  | 'fallback'
export type GuidanceResolutionStatus =
  | 'exact'
  | 'parent_inherited'
  | 'typed_fallback'
  | 'generic_fallback'
  | 'missing'
  | 'stale'
export type RuntimeGuidanceStatus = 'exact' | 'missing' | 'stale' | 'inherited' | 'invalid'

export interface WpContext {
  wpId: string
  wpCode: string
  wpName: string
  componentType: string
  projectId: string
  year: number
  sheetCode: string | null
  sheetName: string
  /** G-ID stable uid; never invent from display name. */
  sheetUid?: string | null
  sheetUidNullReason?: string | null
  host: GuidanceHost
  wholeWorkbook: boolean
  /** Race stamps from host emitter — not part of cache identity. */
  ownerEpoch?: number
  contextRevision?: number
}

export interface GuidanceSourceRef {
  kind: string
  path: string
  sheet?: string
  range?: string
  anchor?: string
  digest?: string
  [key: string]: string | undefined
}

/** Runtime API section payload — NOT the G-C0 wire ``GuidanceSection``. */
export interface RuntimeGuidanceSectionPayload {
  key: string | null
  title: string
  items: string[]
  source_refs: GuidanceSourceRef[]
}

export interface GuidanceResponse {
  wp_code: string
  wp_name: string
  requested_sheet_code: string | null
  requested_sheet_name?: string | null
  resolved_wp_code: string
  inherited_from_parent: boolean
  resolution_status: GuidanceResolutionStatus
  resolution_reason: string
  sheet_identity_reason?: string
  whole_workbook?: boolean
  source: GuidanceSource
  complexity: 'high' | 'medium' | 'low'
  guidance_version: string
  source_digest: string
  generated_at: string
  missing_sections: string[]
  exact_blockers?: string[]
  ai_enabled: boolean
  inventory_run_id?: string | null
  inventory_facts_digest?: string | null
  inventory_entry_id?: string | null
  inventory_entry_digest?: string | null
  runtime_guidance_status?: RuntimeGuidanceStatus | null
  stale_reasons?: string[]
  guidance_required?: boolean | null
  guidance_context_kind?: 'sheet' | 'whole_workbook' | 'template_only' | 'guidance_only' | 'custom_runtime' | null
  etag?: string | null
  completion_status?: 'complete' | 'partial' | 'blocked' | string | null
  resolution_reasons?: string[]
  provenance?: {
    primary?: { kind?: string; source?: string; label?: string; path?: string | null; digest?: string | null; [key: string]: unknown }
    overlays?: Array<{ kind?: string; source?: string; label?: string; path?: string | null; [key: string]: unknown }>
    extraction?: Array<{ kind?: string; source?: string; label?: string; path?: string | null; [key: string]: unknown }>
  } | null
  guidance: {
    sections: RuntimeGuidanceSectionPayload[]
    raw_text: string
  }
  recommended_questions: string[]
}

interface GuidanceCacheRecord {
  schemaVersion: string
  contextIdentity: string
  cachedAt: number
  expiresAt: number
  guidanceVersion: string
  data: GuidanceResponse
}

export interface GuidanceAiContext {
  wpId: string
  projectId: string
  wpCode: string
  sheetCode: string | null
  sheetName: string
  wholeWorkbook: boolean
  resolvedWpCode: string
  resolutionStatus: GuidanceResolutionStatus
  guidanceVersion: string
  sourceDigest: string
}

export const GUIDANCE_CACHE_SCHEMA = 'guidance-response-v2'
export const GUIDANCE_CACHE_TTL_MS = 60_000
const LS_KEY_OPEN = 'gt_guidance_panel_open'
const SS_INDEX_PREFIX = 'gt_guidance_index_v2:'
const SS_DATA_PREFIX = 'gt_guidance_data_v2:'

function loadOpenState(): boolean {
  try {
    return localStorage.getItem(LS_KEY_OPEN) === 'true'
  } catch {
    return false
  }
}

function saveOpenState(open: boolean): void {
  try {
    localStorage.setItem(LS_KEY_OPEN, String(open))
  } catch {
    // Storage 不可用时只影响偏好持久化，不阻断编辑器。
  }
}

function normalizeContext(ctx: WpContext): WpContext {
  return {
    ...ctx,
    wpId: ctx.wpId.trim(),
    wpCode: ctx.wpCode.trim(),
    projectId: ctx.projectId.trim(),
    sheetCode: ctx.sheetCode?.trim() || null,
    sheetName: ctx.sheetName?.trim() || '',
    sheetUid: ctx.sheetUid?.trim() || null,
    sheetUidNullReason: ctx.sheetUidNullReason ?? null,
    host: ctx.host || 'html',
    wholeWorkbook: Boolean(ctx.wholeWorkbook),
    ownerEpoch: ctx.ownerEpoch ?? 0,
    contextRevision: ctx.contextRevision ?? 0,
  }
}

/** 稳定 context key；Univer code 尚未解析时 sheetName 仍能隔离不同原生 tab。
 *  不含 ownerEpoch/contextRevision（瞬态竞态门，不作持久 cache identity）。 */
export function buildGuidanceContextIdentity(ctx: WpContext): string {
  const sheetIdentity = ctx.wholeWorkbook
    ? 'whole-workbook'
    : ctx.sheetUid
      ? `sheet-uid:${ctx.sheetUid}`
      : `sheet:${ctx.sheetCode || 'unresolved'}:${ctx.sheetName || 'unnamed'}`
  return [
    GUIDANCE_CACHE_SCHEMA,
    ctx.projectId,
    ctx.wpId,
    ctx.wpCode,
    ctx.host,
    sheetIdentity,
  ].join('|')
}

function cacheIndexKey(identity: string): string {
  return `${SS_INDEX_PREFIX}${encodeURIComponent(identity)}`
}

/** 数据 key 显式包含 guidance version，避免新旧版本共用同一响应槽。 */
export function buildGuidanceCacheDataKey(identity: string, guidanceVersion: string): string {
  return `${SS_DATA_PREFIX}${encodeURIComponent(identity)}:${encodeURIComponent(guidanceVersion)}`
}

function loadCachedGuidance(identity: string, now = Date.now()): GuidanceResponse | null {
  try {
    const version = sessionStorage.getItem(cacheIndexKey(identity))
    if (!version) return null
    const dataKey = buildGuidanceCacheDataKey(identity, version)
    const raw = sessionStorage.getItem(dataKey)
    if (!raw) return null
    const record = JSON.parse(raw) as GuidanceCacheRecord
    const valid = record.schemaVersion === GUIDANCE_CACHE_SCHEMA
      && record.contextIdentity === identity
      && record.guidanceVersion === version
      && record.expiresAt > now
      && record.data?.guidance_version === version
    if (!valid) {
      sessionStorage.removeItem(dataKey)
      sessionStorage.removeItem(cacheIndexKey(identity))
      return null
    }
    return record.data
  } catch {
    return null
  }
}

function saveCachedGuidance(identity: string, data: GuidanceResponse, now = Date.now()): void {
  if (!data.guidance_version) return
  try {
    const indexKey = cacheIndexKey(identity)
    const previousVersion = sessionStorage.getItem(indexKey)
    if (previousVersion && previousVersion !== data.guidance_version) {
      sessionStorage.removeItem(buildGuidanceCacheDataKey(identity, previousVersion))
    }
    const record: GuidanceCacheRecord = {
      schemaVersion: GUIDANCE_CACHE_SCHEMA,
      contextIdentity: identity,
      cachedAt: now,
      expiresAt: now + GUIDANCE_CACHE_TTL_MS,
      guidanceVersion: data.guidance_version,
      data,
    }
    sessionStorage.setItem(
      buildGuidanceCacheDataKey(identity, data.guidance_version),
      JSON.stringify(record),
    )
    sessionStorage.setItem(indexKey, data.guidance_version)
  } catch {
    // sessionStorage 配额或隐私模式不应阻断真实请求。
  }
}

function requestErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (typeof error?.message === 'string' && error.message.trim()) return error.message
  return '编制说明加载失败，请重试'
}

export const useGuidancePanelStore = defineStore('guidancePanel', () => {
  const isOpen = ref(loadOpenState())
  const wpContext = ref<WpContext | null>(null)
  const guidanceData = ref<GuidanceResponse | null>(null)
  const guidanceLoading = ref(false)
  const guidanceError = ref<string | null>(null)
  const aiEnabled = ref(false)

  const requestId = ref(0)
  const abortController = ref<AbortController | null>(null)

  const contextIdentity = computed(() => (
    wpContext.value ? buildGuidanceContextIdentity(wpContext.value) : ''
  ))

  const sourceLabel = computed(() => {
    const labels: Record<GuidanceSource, string> = {
      template_sheet: '模板说明页',
      template_header: '模板页眉',
      docx_instructions: 'Word 编制说明',
      static_json: '标准方法论',
      typed_fallback: '类型提示',
      fallback: '通用提示',
    }
    return guidanceData.value ? labels[guidanceData.value.source] : '暂无来源'
  })

  const isFallback = computed(() => (
    guidanceData.value?.resolution_status !== 'exact'
  ))

  /** 统一 AI 宿主可读取的只读说明上下文；不再挂载第二套聊天面板。 */
  const aiGuidanceContext = computed<GuidanceAiContext | null>(() => {
    const ctx = wpContext.value
    const data = guidanceData.value
    if (!ctx || !data) return null
    return {
      wpId: ctx.wpId,
      projectId: ctx.projectId,
      wpCode: ctx.wpCode,
      sheetCode: ctx.sheetCode,
      sheetName: ctx.sheetName,
      wholeWorkbook: ctx.wholeWorkbook,
      resolvedWpCode: data.resolved_wp_code,
      resolutionStatus: data.resolution_status,
      guidanceVersion: data.guidance_version,
      sourceDigest: data.source_digest,
    }
  })

  function toggle(): void {
    isOpen.value = !isOpen.value
    saveOpenState(isOpen.value)
  }

  function open(): void {
    isOpen.value = true
    saveOpenState(true)
  }

  function close(): void {
    isOpen.value = false
    saveOpenState(false)
  }

  function resetContextState(): void {
    guidanceData.value = null
    guidanceLoading.value = false
    guidanceError.value = null
    aiEnabled.value = false
  }

  function setWpContext(rawContext: WpContext): void {
    const nextContext = normalizeContext(rawContext)
    const nextIdentity = buildGuidanceContextIdentity(nextContext)
    const prev = wpContext.value
    const identityChanged = contextIdentity.value !== nextIdentity
    const epochChanged = (prev?.ownerEpoch ?? 0) !== (nextContext.ownerEpoch ?? 0)
      || (prev?.contextRevision ?? 0) !== (nextContext.contextRevision ?? 0)
    wpContext.value = nextContext
    // Same subject with newer revision still aborts in-flight fetch.
    if (!identityChanged && !epochChanged) return

    abortController.value?.abort()
    abortController.value = null
    requestId.value += 1
    if (identityChanged) {
      resetContextState()
      const cached = loadCachedGuidance(nextIdentity)
      if (cached) {
        guidanceData.value = cached
        aiEnabled.value = Boolean(cached.ai_enabled)
      }
    }

    // 缓存只作首屏预览；仍发唯一一次请求验证服务端 guidance_version / ETag。
    void fetchGuidance()
  }

  function isResponseCurrent(
    identityAtStart: string,
    currentRequestId: number,
    ownerEpoch: number,
    contextRevision: number,
    controller: AbortController,
  ): boolean {
    const ctx = wpContext.value
    return requestId.value === currentRequestId
      && contextIdentity.value === identityAtStart
      && (ctx?.ownerEpoch ?? 0) === ownerEpoch
      && (ctx?.contextRevision ?? 0) === contextRevision
      && !controller.signal.aborted
  }

  async function fetchGuidance(): Promise<void> {
    const ctx = wpContext.value
    if (!ctx) return
    const identityAtStart = buildGuidanceContextIdentity(ctx)
    const ownerEpochAtStart = ctx.ownerEpoch ?? 0
    const revisionAtStart = ctx.contextRevision ?? 0
    const currentRequestId = ++requestId.value

    abortController.value?.abort()
    const controller = new AbortController()
    abortController.value = controller
    guidanceLoading.value = true
    guidanceError.value = null

    const params = new URLSearchParams()
    if (ctx.wholeWorkbook) {
      params.set('whole_workbook', 'true')
    } else {
      if (ctx.sheetCode) params.set('sheet_code', ctx.sheetCode)
      if (ctx.sheetName) params.set('sheet_name', ctx.sheetName)
      if (ctx.sheetUid) params.set('sheet_uid', ctx.sheetUid)
    }
    const query = params.size > 0 ? `?${params.toString()}` : ''
    const url = `/api/workpapers/${ctx.wpId}/guidance${query}`

    const headers: Record<string, string> = {}
    const preview = guidanceData.value
    if (preview?.etag) {
      headers['If-None-Match'] = preview.etag
    } else if (preview?.guidance_version) {
      headers['If-None-Match'] = `"${preview.guidance_version}"`
    }

    try {
      const data = await api.get<GuidanceResponse>(url, {
        signal: controller.signal,
        headers,
      })
      if (!isResponseCurrent(identityAtStart, currentRequestId, ownerEpochAtStart, revisionAtStart, controller)) {
        return
      }
      guidanceData.value = data
      aiEnabled.value = Boolean(data.ai_enabled)
      saveCachedGuidance(identityAtStart, data)
    } catch (error: any) {
      if (error?.name === 'AbortError' || error?.code === 'ERR_CANCELED') return
      // Axios treats 304 outside 2xx — keep short-TTL preview as confirmed.
      if (error?.response?.status === 304) {
        if (!isResponseCurrent(identityAtStart, currentRequestId, ownerEpochAtStart, revisionAtStart, controller)) {
          return
        }
        return
      }
      if (!isResponseCurrent(identityAtStart, currentRequestId, ownerEpochAtStart, revisionAtStart, controller)) {
        return
      }
      // 请求失败不能继续展示缓存预览或上一个版本。
      guidanceData.value = null
      aiEnabled.value = false
      guidanceError.value = requestErrorMessage(error)
    } finally {
      if (
        requestId.value === currentRequestId
        && contextIdentity.value === identityAtStart
        && (wpContext.value?.ownerEpoch ?? 0) === ownerEpochAtStart
        && (wpContext.value?.contextRevision ?? 0) === revisionAtStart
      ) {
        guidanceLoading.value = false
        if (abortController.value === controller) abortController.value = null
      }
    }
  }

  async function refreshGuidance(): Promise<void> {
    guidanceData.value = null
    aiEnabled.value = false
    guidanceError.value = null
    await fetchGuidance()
  }

  function clearWpContext(expectedIdentity?: string): boolean {
    if (expectedIdentity && contextIdentity.value !== expectedIdentity) return false
    abortController.value?.abort()
    abortController.value = null
    requestId.value += 1
    wpContext.value = null
    resetContextState()
    return true
  }

  return {
    isOpen,
    wpContext,
    guidanceData,
    guidanceLoading,
    guidanceError,
    aiEnabled,
    requestId,
    contextIdentity,
    sourceLabel,
    isFallback,
    aiGuidanceContext,
    toggle,
    open,
    close,
    setWpContext,
    refreshGuidance,
    clearWpContext,
  }
})
