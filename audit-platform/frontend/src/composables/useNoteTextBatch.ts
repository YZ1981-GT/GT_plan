/**
 * useNoteTextBatch — 附注正文批量导入/预览/应用 composable
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Phase 6 Task 34
 *
 * 管理来源、映射、draft hash、preview/apply、mutation ID、冲突与进度。
 * 状态以 original/draft hash 判"已编辑"，不依赖布尔标记。
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'
import { v4 as uuidv4 } from 'uuid'

// ── Types ────────────────────────────────────────────────────────────────────

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
}

export interface PreviewItem {
  source_id: string
  target_note_id: string | null
  target_note_section: string | null
  match_kind: string
  evidence: string
  confidence: MatchConfidence
  category: PreviewCategory
  unavailable_reason: string | null
  before_html: string
  proposed_html: string
  before_hash: string
  proposed_hash: string
  expected_updated_at: string | null
  default_mode: ApplyMode
  quality_flags: string[]
  replacements: Array<{
    replacement_id: string
    variable: string
    old_value: string
    new_value: string
    reversible: boolean
  }>
}

export interface PreviewResponse {
  preview_digest: string
  items: PreviewItem[]
  summary: Record<string, number>
  warnings: string[]
}

export interface ApplyResponse {
  application_id: string
  mutation_id: string
  applied_count: number
  summary: Record<string, number>
  changed_note_ids: string[]
  warnings: string[]
  replayed: boolean
}

// ── API Paths ────────────────────────────────────────────────────────────────

const PATHS = {
  parseUpload: (pid: string) => `/api/projects/${pid}/disclosure-note-import/parse-upload`,
  parseKnowledge: (pid: string) => `/api/projects/${pid}/disclosure-note-import/parse-knowledge`,
  preview: (pid: string) => `/api/projects/${pid}/disclosure-note-text-batch/preview`,
  apply: (pid: string) => `/api/projects/${pid}/disclosure-note-text-batch/apply`,
  sections: (pid: string) => `/api/projects/${pid}/disclosure-note-text-sections`,
}

// ── Composable ───────────────────────────────────────────────────────────────

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
  const parsedSections = ref<ParsedSection[]>([])
  const previewResult = ref<PreviewResponse | null>(null)
  const applyResult = ref<ApplyResponse | null>(null)
  const lastError = ref<string>('')

  // draft 状态用 hash 判定
  const draftHashes = ref<Map<string, string>>(new Map())
  const originalHashes = ref<Map<string, string>>(new Map())

  const isDirty = computed(() => {
    for (const [key, hash] of draftHashes.value) {
      if (hash !== originalHashes.value.get(key)) return true
    }
    return false
  })

  const mutationId = ref(uuidv4())

  function resetMutationId() {
    mutationId.value = uuidv4()
  }

  // ── 上传解析 ──────────────────────────────────────────────────────────

  async function parseUpload(file: File): Promise<void> {
    loading.value = true
    lastError.value = ''
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('year', String(year.value))
      const result = await api.post<{ sections: ParsedSection[]; warnings: string[] }>(
        PATHS.parseUpload(projectId.value),
        formData,
      )
      parsedSections.value = result.sections || []
      sourceKind.value = 'upload'
      if (result.warnings?.length) {
        ElMessage.warning(result.warnings[0])
      }
    } catch (e: any) {
      lastError.value = e?.response?.data?.detail?.message || e?.message || '解析失败'
      ElMessage.error(lastError.value)
    } finally {
      loading.value = false
    }
  }

  // ── 知识库解析 ────────────────────────────────────────────────────────

  async function parseKnowledge(docIds: string[]): Promise<void> {
    loading.value = true
    lastError.value = ''
    try {
      const result = await api.post<{ sections: ParsedSection[]; warnings: string[] }>(
        PATHS.parseKnowledge(projectId.value),
        { year: year.value, doc_ids: docIds },
      )
      parsedSections.value = result.sections || []
      sourceKind.value = 'knowledge'
    } catch (e: any) {
      lastError.value = e?.response?.data?.detail?.message || e?.message || '解析失败'
      ElMessage.error(lastError.value)
    } finally {
      loading.value = false
    }
  }

  // ── Preview ───────────────────────────────────────────────────────────

  async function fetchPreview(manualMappings?: Array<{ source_id: string; target_note_id: string }>): Promise<void> {
    previewLoading.value = true
    lastError.value = ''
    try {
      const body = {
        year: year.value,
        source: {
          source_kind: sourceKind.value,
          parsed_source: {
            source_kind: sourceKind.value,
            sections: parsedSections.value,
          },
        },
        manual_mappings: manualMappings || [],
      }
      previewResult.value = await api.post<PreviewResponse>(
        PATHS.preview(projectId.value),
        body,
      )
      // 记录 original hash
      originalHashes.value.clear()
      draftHashes.value.clear()
      for (const item of previewResult.value?.items || []) {
        originalHashes.value.set(item.source_id, item.proposed_hash)
        draftHashes.value.set(item.source_id, item.proposed_hash)
      }
    } catch (e: any) {
      lastError.value = e?.response?.data?.detail?.message || e?.message || '预览失败'
      ElMessage.error(lastError.value)
    } finally {
      previewLoading.value = false
    }
  }

  // ── Apply ─────────────────────────────────────────────────────────────

  async function applyBatch(
    selections: Array<{
      source_id: string
      target_note_id: string
      mode: ApplyMode
      before_hash: string
      proposed_hash: string
      proposed_html: string
    }>,
  ): Promise<ApplyResponse | null> {
    if (!previewResult.value) {
      ElMessage.error('请先预览')
      return null
    }
    applyLoading.value = true
    lastError.value = ''
    try {
      const body = {
        year: year.value,
        source: {
          source_kind: sourceKind.value,
          parsed_source: {
            source_kind: sourceKind.value,
            sections: parsedSections.value,
          },
        },
        preview_digest: previewResult.value.preview_digest,
        selections,
      }
      const result = await api.post<ApplyResponse>(
        PATHS.apply(projectId.value),
        body,
        { headers: { 'X-Mutation-Id': mutationId.value } },
      )
      applyResult.value = result
      ElMessage.success(`已成功应用 ${result.applied_count} 个章节`)
      resetMutationId()
      return result
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (detail?.error_code === 'NOTE_BATCH_STALE_PREVIEW') {
        lastError.value = '部分章节在预览后已被修改，请重新预览'
        ElMessage.warning(lastError.value)
      } else if (detail?.error_code === 'MUTATION_ID_CONFLICT') {
        lastError.value = '请求已提交，请勿重复操作'
        ElMessage.warning(lastError.value)
      } else {
        lastError.value = detail?.message || e?.message || '应用失败'
        ElMessage.error(lastError.value)
      }
      return null
    } finally {
      applyLoading.value = false
    }
  }

  function reset() {
    parsedSections.value = []
    previewResult.value = null
    applyResult.value = null
    lastError.value = ''
    draftHashes.value.clear()
    originalHashes.value.clear()
    resetMutationId()
  }

  return {
    // state
    loading,
    previewLoading,
    applyLoading,
    sourceKind,
    parsedSections,
    previewResult,
    applyResult,
    lastError,
    isDirty,
    mutationId,
    // actions
    parseUpload,
    parseKnowledge,
    fetchPreview,
    applyBatch,
    reset,
    resetMutationId,
  }
}
