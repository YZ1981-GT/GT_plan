/**
 * useNoteTextBatch — 附注正文批量导入 / 预览 / 应用 composable
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Task 34（第二轮复盘：对齐后端契约 + R-23）
 *
 * 来源可信度由后端裁定，这里只负责「原样回传」：
 * - 上传：parse-upload 的整份响应（含服务端签名的 source_metadata）作为 parsed_source 回传，章节正文可二次编辑；
 * - 知识库：解析结果 + knowledge_doc_ids（后端每次 preview / apply 重新判权）；
 * - 内容模板：只传 template_version_id + template_content_hash，不传正文。
 * apply 必须带上与最近一次 preview 完全相同的来源 / 手工映射 / 撤销项（后端重算并比对 digest），
 * 所以预览后的任何修改都会把预览标为过期，必须重新预览才能应用。
 * 「已编辑」按原文与当前正文逐章比对，不用易漂移的布尔标记（AC-2.5）。
 */
import { computed, ref, type Ref } from 'vue'
import type { AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { parseApiError } from '@/composables/useApiError'
import { eventBus } from '@/utils/eventBus'
import { newUuid } from '@/utils/uuid'

export type SourceKind = 'upload' | 'knowledge' | 'content_template'
export type ApplyMode = 'replace' | 'append'
export type MatchConfidence = 'confirmed' | 'candidate' | 'manual_required'
export type PreviewCategory = 'recommended' | 'review' | 'unavailable'

export interface ParsedSection {
  source_id: string
  title: string
  level: number
  html: string
  confidence: MatchConfidence
  warnings: string[]
  metadata?: Record<string, unknown>
}

/** parse-upload / parse-knowledge 的响应；preview / apply 原样回传（含服务端签名元数据） */
export interface ParsedSource {
  source_kind: 'upload' | 'knowledge'
  source_metadata: Record<string, unknown>
  sections: ParsedSection[]
  warnings: string[]
  needs_ocr: boolean
}

export interface Replacement {
  replacement_id: string
  variable: string
  old_value: string
  new_value: string
  reversible: boolean
  revoked?: boolean
}

export interface PreviewItem {
  source_id: string
  source_title: string
  target_note_id: string | null
  target_note_section: string | null
  target_section_title: string | null
  /** 目标所属一级章标题（右栏按章分组用，AC-2.3） */
  target_chapter_title?: string | null
  match_kind: string
  evidence: string
  confidence: MatchConfidence
  category: PreviewCategory
  default_selected: boolean
  unavailable_reason: string | null
  before_html: string
  before_hash: string
  proposed_html: string
  proposed_hash: string
  append_html: string | null
  append_hash: string | null
  expected_updated_at: string | null
  default_mode: ApplyMode
  quality_flags: string[]
  replacements: Replacement[]
}

export interface PreviewResponse {
  preview_digest: string
  items: PreviewItem[]
  /** 不进预览的来源及原因（folded 已并入上级 / out_of_scope 不在可填范围），左栏显示匹配状态用（AC-2.2） */
  skipped_sources?: Array<{ source_id: string; match_kind: string }>
  summary: Record<string, number>
  warnings: string[]
}

export interface ApplyResponse {
  application_id: string
  mutation_id: string
  applied_count: number
  summary: Record<string, number>
  changed_notes: Array<{ id: string; note_section: string }>
  changed_note_ids: string[]
  event_delivery?: 'published' | 'partial' | 'failed'
  warnings: Array<string | { code?: string; message?: string }>
}

/** 批次回执：写入章数 + 替换 / 追加分布（summary 即后端 mode_summary）；替换与追加对正文的影响不同，必须分开报 */
export function receiptText(result: Pick<ApplyResponse, 'applied_count'> & { summary?: Record<string, number> }): string {
  const parts = ([['替换', result.summary?.replace], ['追加', result.summary?.append]] as const)
    .filter(([, n]) => (n ?? 0) > 0).map(([label, n]) => `${label} ${n}`)
  return `已写入 ${result.applied_count} 个章节${parts.length ? `（${parts.join(' · ')}）` : ''}`
}

export interface ApplySelection {
  source_id: string
  target_note_id: string
  mode: ApplyMode
  before_hash: string
  proposed_hash: string
  expected_updated_at: string | null
}

export interface TargetSection {
  id: string
  note_section: string
  section_title: string
  section_kind: string
  has_content: boolean
  chapter_title?: string | null
}

export interface BatchError {
  code: string
  message: string
  staleNotes: string[]
}

export const NOTE_TEXT_BATCH_PATHS = {
  parseUpload: (pid: string) => `/api/projects/${pid}/disclosure-note-import/parse-upload`,
  parseKnowledge: (pid: string) => `/api/projects/${pid}/disclosure-note-import/parse-knowledge`,
  preview: (pid: string) => `/api/projects/${pid}/disclosure-note-text-batch/preview`,
  apply: (pid: string) => `/api/projects/${pid}/disclosure-note-text-batch/apply`,
  sections: (pid: string) => `/api/projects/${pid}/disclosure-note-text-sections`,
  sources: (pid: string) => `/api/projects/${pid}/disclosure-note-text-batch/sources`,
}

/** 各章最近一次批量写入的来源（GET …/disclosure-note-text-batch/sources，Task 50 编辑器来源标记） */
export interface NoteTextSource {
  application_id: string
  source_kind: SourceKind
  mode: ApplyMode | null
  source_title: string | null
  applied_at: string | null
  applied_by_name: string | null
  /** 当前已保存正文与该次写入结果不同（写入后有人改过） */
  modified_after: boolean
  template_name?: string | null
  version_no?: number | null
  file_name?: string | null
  documents?: Array<{ document_name: string | null; doc_version: number | null }>
}

/** 可重试：传输层错误或同键请求仍在处理 ⇒ 保留同一幂等键重发，后端返回同一结果 */
const RETRYABLE = new Set(['NETWORK_ERROR', 'TIMEOUT', 'MUTATION_IN_PROGRESS'])
/** 预览已不再代表服务端现状：必须重新预览 */
const PREVIEW_OUTDATED = new Set(['NOTE_BATCH_STALE_PREVIEW', 'PREVIEW_DIGEST_MISMATCH', 'MUTATION_ID_CONFLICT'])

/**
 * 本模块请求一律静默全局拦截器：错误由 {@link notifyBatchError} 中文化后只提示一次。
 * 不静默时拦截器先弹一次（422 直接显示 pydantic 英文、403 只有笼统「权限不足」），catch 里再弹一次。
 */
export function silent(config?: AxiosRequestConfig): AxiosRequestConfig {
  const cfg = { ...config, _silent: true }
  return cfg
}

/** 被同一请求的新一发取代（http 去重 abort）——不是失败，状态归新请求 */
export function isCanceled(e: unknown): boolean {
  const err = e as { code?: string; name?: string } | null
  return err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError'
}

/** 后端错误 → 统一结构；后端 message 已是中文，校验错误（pydantic 英文）与 axios 英文兜底换成中文 */
export function toBatchError(e: unknown, fallback: string): BatchError {
  if (isCanceled(e)) return { code: 'CANCELED', message: '', staleNotes: [] }
  const parsed = parseApiError(e)
  const detail = (parsed.detail ?? {}) as { stale_notes?: unknown }
  const status = (e as { response?: { status?: number } } | null)?.response?.status
  // REQUEST_ERROR 带 response = 无业务 detail 的 HTTP 错误，message 是 axios 英文；不带 = 本地中文异常
  const message = parsed.code === 'VALIDATION_ERROR' ? '请求参数不合法，请刷新页面后重试'
    : parsed.code === 'UNKNOWN' ? fallback
      : parsed.code === 'REQUEST_ERROR' && status ? `${fallback}（HTTP ${status}）`
        : parsed.message || fallback
  return {
    code: parsed.code,
    message,
    staleNotes: Array.isArray(detail.stale_notes) ? detail.stale_notes.map(String) : [],
  }
}

/**
 * 统一失败出口：中文提示一次；合并锁定 423 通知锁定横幅刷新（静默后全局拦截器不再代发）。
 * ``subject`` 是出错对象（如文件名）：解析失败不清空当前来源，提示必须分清是哪个文件失败。
 */
export function notifyBatchError(e: unknown, fallback: string, projectId: string, notify = true,
  subject = ''): BatchError {
  const err = toBatchError(e, fallback)
  if (err.code === 'CANCELED') return err
  const status = (e as { response?: { status?: number } } | null)?.response?.status
  if (status === 423 && err.message.includes('合并锁定')) eventBus.emit('consol-lock:detected', { projectId })
  if (subject) err.message = `${subject}：${err.message}`
  if (notify) ElMessage.error(err.message)
  return err
}

/** 预览项 → apply selection；追加模式提交预演出的 append_hash（后端逐字比对） */
export function toSelection(item: PreviewItem, mode: ApplyMode): ApplySelection {
  return {
    source_id: item.source_id,
    target_note_id: item.target_note_id as string,
    mode,
    before_hash: item.before_hash,
    proposed_hash: (mode === 'append' ? item.append_hash : item.proposed_hash) as string,
    expected_updated_at: item.expected_updated_at,
  }
}

export interface UseNoteTextBatchOptions {
  projectId: Ref<string>
  year: Ref<number>
}

export function useNoteTextBatch(options: UseNoteTextBatchOptions) {
  const { projectId, year } = options

  const loading = ref(false)
  const previewLoading = ref(false)
  const applyLoading = ref(false)

  const sourceKind = ref<SourceKind>('upload')
  const parsedSource = ref<ParsedSource | null>(null)
  const knowledgeDocIds = ref<string[]>([])
  const templateSource = ref<{ versionId: string; contentHash: string } | null>(null)
  const manualMappings = ref<Map<string, string>>(new Map())
  const revokedReplacementIds = ref<Set<string>>(new Set())

  const previewResult = ref<PreviewResponse | null>(null)
  /** 预览后改过正文 / 映射 / 撤销项 ⇒ 预览不再代表将写入的内容，必须重新预览 */
  const previewStale = ref(false)
  const applyResult = ref<ApplyResponse | null>(null)
  const lastError = ref<BatchError | null>(null)

  /** 来源原文（逐章），「已编辑」= 当前正文与原文不同 */
  const originalHtml = ref<Map<string, string>>(new Map())
  const parsedSections = computed<ParsedSection[]>(() => parsedSource.value?.sections ?? [])
  const editedSourceIds = computed(() =>
    parsedSections.value.filter(s => s.html !== originalHtml.value.get(s.source_id)).map(s => s.source_id))
  const isDirty = computed(() => editedSourceIds.value.length > 0 || manualMappings.value.size > 0)
  const canApply = computed(() => !!previewResult.value && !previewStale.value && !applyLoading.value)

  const mutationId = ref(newUuid())
  function resetMutationId() {
    mutationId.value = newUuid()
  }

  function fail(e: unknown, fallback: string, subject = ''): BatchError {
    lastError.value = notifyBatchError(e, fallback, projectId.value, true, subject)
    return lastError.value
  }

  /** 前端拒收文件（扩展名 / 大小）：与服务端失败走同一个 lastError，不残留上一次的错误提示 */
  function rejectFile(fileName: string, reason: string) {
    lastError.value = { code: 'INVALID_FILE', message: `${fileName}：${reason}`, staleNotes: [] }
    ElMessage.error(lastError.value.message)
  }

  function clearPreview() {
    previewResult.value = null
    previewStale.value = false
    resetMutationId()
  }

  function loadSource(kind: SourceKind, source: ParsedSource | null) {
    sourceKind.value = kind
    parsedSource.value = source
    originalHtml.value = new Map((source?.sections ?? []).map(s => [s.source_id, s.html]))
    manualMappings.value = new Map()
    revokedReplacementIds.value = new Set()
    applyResult.value = null
    lastError.value = null
    clearPreview()
  }

  // ── 来源 ─────────────────────────────────────────────────────────────

  async function parseUpload(file: File): Promise<boolean> {
    loading.value = true
    lastError.value = null
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await api.post<ParsedSource>(NOTE_TEXT_BATCH_PATHS.parseUpload(projectId.value), form, silent())
      loadSource('upload', result)
      knowledgeDocIds.value = []
      templateSource.value = null
      if (result.warnings?.length) ElMessage.warning(result.warnings[0])
      return true
    } catch (e) {
      fail(e, '文档解析失败', file.name)
      return false
    } finally {
      loading.value = false
    }
  }

  async function parseKnowledge(docIds: string[]): Promise<boolean> {
    loading.value = true
    lastError.value = null
    try {
      const result = await api.post<ParsedSource>(NOTE_TEXT_BATCH_PATHS.parseKnowledge(projectId.value),
        { year: year.value, doc_ids: docIds }, silent())
      loadSource('knowledge', result)
      knowledgeDocIds.value = [...docIds]
      templateSource.value = null
      if (result.warnings?.length) ElMessage.warning(result.warnings.join('；'))
      return true
    } catch (e) {
      fail(e, '知识库文档解析失败')
      return false
    } finally {
      loading.value = false
    }
  }

  function useTemplateVersion(versionId: string, contentHash: string) {
    loadSource('content_template', null)
    knowledgeDocIds.value = []
    templateSource.value = { versionId, contentHash }
  }

  function buildSource(): Record<string, unknown> {
    if (sourceKind.value === 'content_template') {
      if (!templateSource.value) throw new Error('未选择模板版本')
      return { source_kind: 'content_template', template_version_id: templateSource.value.versionId,
        template_content_hash: templateSource.value.contentHash }
    }
    if (!parsedSource.value) throw new Error('尚未解析来源')
    const source: Record<string, unknown> = { source_kind: sourceKind.value, parsed_source: parsedSource.value }
    if (sourceKind.value === 'knowledge') source.knowledge_doc_ids = knowledgeDocIds.value
    return source
  }

  // ── 用户修改（都会让预览过期）──────────────────────────────────────────

  function updateSectionHtml(sourceId: string, html: string) {
    const section = parsedSource.value?.sections.find(s => s.source_id === sourceId)
    if (!section || section.html === html) return
    section.html = html
    if (previewResult.value) previewStale.value = true
  }

  function setManualMapping(sourceId: string, targetNoteId: string | null) {
    const next = new Map(manualMappings.value)
    if (targetNoteId) next.set(sourceId, targetNoteId)
    else next.delete(sourceId)
    manualMappings.value = next
    if (previewResult.value) previewStale.value = true
  }

  function toggleRevocation(replacementId: string) {
    const next = new Set(revokedReplacementIds.value)
    if (next.has(replacementId)) next.delete(replacementId)
    else next.add(replacementId)
    revokedReplacementIds.value = next
    if (previewResult.value) previewStale.value = true
  }

  function mappingPayload() {
    return [...manualMappings.value].map(([source_id, target_note_id]) => ({ source_id, target_note_id }))
  }

  // ── 预览 / 应用 ────────────────────────────────────────────────────────

  async function fetchPreview(): Promise<boolean> {
    previewLoading.value = true
    lastError.value = null
    try {
      previewResult.value = await api.post<PreviewResponse>(NOTE_TEXT_BATCH_PATHS.preview(projectId.value), {
        year: year.value,
        source: buildSource(),
        manual_mappings: mappingPayload(),
        revoked_replacement_ids: [...revokedReplacementIds.value],
      }, silent())
      previewStale.value = false
      resetMutationId()  // 新预览 = 新载荷，旧幂等键不得复用（同键不同载荷 409）
      return true
    } catch (e) {
      fail(e, '预览失败')
      return false
    } finally {
      previewLoading.value = false
    }
  }

  async function applyBatch(selections: ApplySelection[]): Promise<ApplyResponse | null> {
    if (!previewResult.value || previewStale.value) {
      ElMessage.warning('预览已过期，请先重新预览')
      return null
    }
    if (!selections.length) {
      ElMessage.warning('请至少选择一个章节')
      return null
    }
    applyLoading.value = true
    lastError.value = null
    try {
      const result = await api.post<ApplyResponse>(NOTE_TEXT_BATCH_PATHS.apply(projectId.value), {
        year: year.value,
        source: buildSource(),
        preview_digest: previewResult.value.preview_digest,
        selections,
        manual_mappings: mappingPayload(),
        revoked_replacement_ids: [...revokedReplacementIds.value],
      }, silent({ headers: { 'X-Mutation-Id': mutationId.value } }))
      applyResult.value = result
      eventBus.emit('note-text-batch:applied', { projectId: projectId.value, year: year.value })
      ElMessage.success(receiptText(result))
      if (result.event_delivery && result.event_delivery !== 'published') {
        ElMessage.warning('内容已保存，但部分章节的联动通知发送失败，请刷新页面确认')
      }
      resetMutationId()
      return result
    } catch (e) {
      // 草稿与选择全部保留（AC-4.3 原子失败不丢编辑）；后端 message 已列出冲突章节
      const err = fail(e, '写入失败')
      if (PREVIEW_OUTDATED.has(err.code)) previewStale.value = true
      if (!RETRYABLE.has(err.code)) resetMutationId()
      return null
    } finally {
      applyLoading.value = false
    }
  }

  async function fetchTargetSections(): Promise<TargetSection[]> {
    try {
      const result = await api.get<{ items: TargetSection[] }>(NOTE_TEXT_BATCH_PATHS.sections(projectId.value),
        silent({ params: { year: year.value, scope: sourceKind.value === 'content_template' ? 'all' : 'narrative' } }))
      return result.items || []
    } catch (e) {
      fail(e, '加载目标章节失败')
      return []
    }
  }

  function reset() {
    loadSource('upload', null)
    knowledgeDocIds.value = []
    templateSource.value = null
  }

  return {
    loading, previewLoading, applyLoading,
    sourceKind, parsedSource, parsedSections, knowledgeDocIds, templateSource,
    manualMappings, revokedReplacementIds, previewResult, previewStale, applyResult, lastError,
    editedSourceIds, isDirty, canApply, mutationId,
    parseUpload, parseKnowledge, rejectFile, useTemplateVersion, updateSectionHtml, setManualMapping, toggleRevocation,
    fetchPreview, applyBatch, fetchTargetSections, clearPreview, reset, resetMutationId,
  }
}
