/**
 * useReviewEvidenceDisplay — 复核证据展示 composable（Task 6.5, Wave 5）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R9, R10, R12
 * Design: §4.6, §5.4
 *
 * R10.4: QC/EQCR 查看证据时 SHALL 展示来源版本、哈希、人工确认记录、stale 状态
 * 及可定位引用，不得只展示脱离来源的摘录。
 *
 * 提供：
 *  - 复核证据快照展示数据加载
 *  - 版本/hash/OCR确认/AI确认/stale path/locator 完整展示
 *  - QC/EQCR/partner 完成阻断状态检查
 */

import { ref, computed, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ReviewEvidenceSnapshotDisplay {
  evidence_ref_id: string
  evidence_type: string
  source_version: number
  content_hash: string
  /** OCR 人工确认状态 */
  ocr_confirmed: boolean
  ocr_confirmation_at: string | null
  ocr_confirmed_by: string | null
  /** AI 确认状态 */
  ai_confirmed: boolean
  ai_confirmation_at: string | null
  ai_confirmed_by: string | null
  /** stale 状态 */
  is_stale: boolean
  stale_path: string[]
  /** 可定位引用 (opaque locator / download URL / page+region) */
  locator: string
  locator_type: 'opaque' | 'download_url' | 'page_region'
}

export interface ReviewOpinionDisplay {
  opinion_id: string
  status: 'open' | 'closed' | 're_review_required'
  severity: string
  content: string
  created_by: string
  closed_by: string | null
  closing_explanation: string | null
  created_at: string
  closed_at: string | null
  evidence_items: ReviewEvidenceSnapshotDisplay[]
}

export interface CompletionBlockStatus {
  blocked: boolean
  blocking_opinions: Array<{
    opinion_id: string
    severity: string
    status: string
    content: string
  }>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useReviewEvidenceDisplay(
  projectId: Ref<string>,
  year: Ref<number>
) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const opinions = ref<ReviewOpinionDisplay[]>([])
  const completionStatus = ref<CompletionBlockStatus>({
    blocked: false,
    blocking_opinions: [],
  })

  const basePath = () =>
    `/api/projects/${projectId.value}/years/${year.value}/evidence`

  /**
   * 加载复核意见及其完整证据展示（R10.4）
   */
  async function loadOpinionEvidence(
    opinionId: string
  ): Promise<ReviewOpinionDisplay | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(
        `${basePath()}/reviews/${opinionId}/evidence-display`
      )
      const data = res.data?.data || res.data
      return data as ReviewOpinionDisplay
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 加载目标关联的所有复核意见证据（用于 QC/EQCR 视图）
   */
  async function loadTargetReviewEvidence(params: {
    target_type: string
    target_id: string
  }): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/reviews/evidence-display`, {
        params,
      })
      const data = res.data?.data || res.data
      opinions.value = data.opinions || []
    } catch (e: any) {
      error.value = _extractError(e)
      opinions.value = []
    } finally {
      loading.value = false
    }
  }

  /**
   * 检查 QC/EQCR/partner 完成是否被阻断（R10.3）
   */
  async function checkCompletionBlocked(params: {
    target_type: string
    target_id: string
  }): Promise<CompletionBlockStatus> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/reviews/completion-status`, {
        params,
      })
      const data = res.data?.data || res.data
      completionStatus.value = data as CompletionBlockStatus
      return completionStatus.value
    } catch (e: any) {
      error.value = _extractError(e)
      completionStatus.value = { blocked: false, blocking_opinions: [] }
      return completionStatus.value
    } finally {
      loading.value = false
    }
  }

  /** 是否存在 stale 证据项 */
  const hasStaleEvidence = computed(() =>
    opinions.value.some((op) =>
      op.evidence_items.some((item) => item.is_stale)
    )
  )

  /** 是否存在待重新复核的意见 */
  const hasReReviewRequired = computed(() =>
    opinions.value.some((op) => op.status === 're_review_required')
  )

  /** 完成是否被阻断 */
  const isCompletionBlocked = computed(() => completionStatus.value.blocked)

  return {
    // state
    loading,
    error,
    opinions,
    completionStatus,
    // computed
    hasStaleEvidence,
    hasReReviewRequired,
    isCompletionBlocked,
    // methods
    loadOpinionEvidence,
    loadTargetReviewEvidence,
    checkCompletionBlocked,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _extractError(e: any): string {
  const data = e?.response?.data
  const payload = data?.data || data
  if (payload?.error_code === 'SCOPE_NOT_FOUND_OR_FORBIDDEN') {
    return '目标不可访问'
  }
  if (payload?.error_code) {
    return payload.message || '操作失败'
  }
  return e?.message || '网络错误'
}
