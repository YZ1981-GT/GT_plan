/**
 * useReviewGovernance — 复核证据绑定/关闭/重开 API composable（Wave 5/9 前端接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R9, R10, R12
 * Design: §6.2 主要端点 (Review)
 *
 * 后端路由（review_evidence_router）：
 *  - GET  /reviews/{id}              复核状态 + 证据展示（版本/hash/stale/locator）
 *  - POST /reviews/{id}/evidence     绑定证据（冻结 raised 快照）
 *  - POST /reviews/{id}/close        关闭复核（权限+说明+非 stale ref 门禁）
 *  - POST /reviews/{id}/reopen       依据失效自动重开 → re_review_required
 *  - GET  /reviews/completion-block  QC/EQCR/partner 完成是否被阻断
 *
 * 注：与既有 useReviewEvidenceDisplay（指向未实现端点）不同，本 composable
 * 对齐已上线的 review_evidence_router 真实端点。
 */

import { ref, computed, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ReviewEvidenceItem {
  evidence_ref_id: string
  evidence_type: string
  target_version: number | null
  content_hash: string | null
  is_stale: boolean
  locator: Record<string, unknown> | null
}

export interface ReviewState {
  review_id: string
  status: 'open' | 'closed' | 're_review_required'
  close_note: string | null
  closed_by_user_id: string | null
  closed_at: string | null
  reopened_at: string | null
  evidence: ReviewEvidenceItem[]
}

export interface CompletionBlock {
  blocked: boolean
  re_review_required_reviews: string[]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useReviewGovernance(projectId: Ref<string>, year: Ref<number>) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const reviewState = ref<ReviewState | null>(null)
  const completion = ref<CompletionBlock>({ blocked: false, re_review_required_reviews: [] })

  const basePath = () =>
    `/api/projects/${projectId.value}/years/${year.value}/evidence/reviews`

  async function getReview(reviewId: string): Promise<ReviewState | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/${reviewId}`)
      reviewState.value = (res.data?.data ?? res.data) as ReviewState
      return reviewState.value
    } catch (e: any) {
      error.value = _extractError(e)
      reviewState.value = null
      return null
    } finally {
      loading.value = false
    }
  }

  async function bindEvidence(
    reviewId: string,
    params: {
      evidence_ref_id: string
      target_version?: number | null
      target_hash?: string | null
      locator?: Record<string, unknown> | null
    },
  ): Promise<any | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/${reviewId}/evidence`, params)
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function closeReview(
    reviewId: string,
    closingExplanation: string,
    severity: 'low' | 'medium' | 'high' | 'critical' = 'high',
  ): Promise<any | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/${reviewId}/close`, {
        closing_explanation: closingExplanation,
        severity,
      })
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function reopenReview(reviewId: string, reason = 'evidence_invalidated'): Promise<any | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/${reviewId}/reopen`, { reason })
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function checkCompletionBlock(): Promise<CompletionBlock> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/completion-block`)
      completion.value = (res.data?.data ?? res.data) as CompletionBlock
      return completion.value
    } catch (e: any) {
      error.value = _extractError(e)
      completion.value = { blocked: false, re_review_required_reviews: [] }
      return completion.value
    } finally {
      loading.value = false
    }
  }

  const hasStaleEvidence = computed(
    () => !!reviewState.value?.evidence.some((it) => it.is_stale),
  )

  return {
    loading,
    error,
    reviewState,
    completion,
    hasStaleEvidence,
    getReview,
    bindEvidence,
    closeReview,
    reopenReview,
    checkCompletionBlock,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _extractError(e: any): string {
  const data = e?.response?.data
  const payload = data?.data || data
  if (payload?.error_code === 'SCOPE_NOT_FOUND_OR_FORBIDDEN') return '目标不可访问'
  if (payload?.error_code === 'EVIDENCE_GATE_BLOCKED') return payload.message || '复核关闭门禁未通过'
  if (payload?.error_code === 'INVALID_STATE_TRANSITION') return payload.message || '状态迁移非法'
  if (payload?.error_code) return payload.message || '操作失败'
  return e?.message || '网络错误'
}
