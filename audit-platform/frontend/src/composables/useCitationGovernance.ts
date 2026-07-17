/**
 * useCitationGovernance — 引用快照定位 API composable（Wave 5/9 前端接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R7, R9, R15
 * Design: §6.2 主要端点 (RAG/AI — citation)
 *
 * 后端路由（citation_router）：
 *  - GET  /citations                    列出本 scope 引用快照（可按 ai_content_log_id 过滤）
 *  - GET  /citations/{id}/locate        定位/打开引用（打开时重新鉴权）
 *  - POST /citations/validate           批量校验引用集合
 */

import { ref, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CitationSnapshotItem {
  id: string
  ai_content_log_id: string
  evidence_ref_id: string
  audit_year: number | null
  target_version: number | null
  target_hash: string | null
  page: number | null
  region: string | null
  excerpt_hash: string | null
  index_version: string | null
  locator_version: string | null
  created_at: string | null
}

export interface CitationLocateResult {
  citation_id: string
  status: string
  readable: boolean
  version_valid: boolean
  hash_valid: boolean
  source_available: boolean
  locator: string | null
  page: number | null
  region: string | null
  reason: string | null
}

export interface CitationValidateEntry {
  citation_id: string
  status: string
  reason: string | null
}

export interface CitationValidateResult {
  all_valid: boolean
  valid: CitationValidateEntry[]
  stale: CitationValidateEntry[]
  invalid: CitationValidateEntry[]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useCitationGovernance(projectId: Ref<string>, year: Ref<number>) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const citations = ref<CitationSnapshotItem[]>([])

  const basePath = () =>
    `/api/projects/${projectId.value}/years/${year.value}/evidence/citations`

  async function listCitations(params?: {
    ai_content_log_id?: string
    limit?: number
  }): Promise<CitationSnapshotItem[]> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(basePath(), { params })
      const data = res.data?.data ?? res.data
      citations.value = data?.items || []
      return citations.value
    } catch (e: any) {
      error.value = _extractError(e)
      citations.value = []
      return []
    } finally {
      loading.value = false
    }
  }

  async function locateCitation(citationId: string): Promise<CitationLocateResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/${citationId}/locate`)
      return (res.data?.data ?? res.data) as CitationLocateResult
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function validateCitations(citationIds: string[]): Promise<CitationValidateResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/validate`, { citation_ids: citationIds })
      return (res.data?.data ?? res.data) as CitationValidateResult
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    citations,
    listCitations,
    locateCitation,
    validateCitations,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _extractError(e: any): string {
  const data = e?.response?.data
  const payload = data?.data || data
  if (payload?.error_code === 'SCOPE_NOT_FOUND_OR_FORBIDDEN') return '目标不可访问'
  if (payload?.error_code) return payload.message || '操作失败'
  return e?.message || '网络错误'
}
