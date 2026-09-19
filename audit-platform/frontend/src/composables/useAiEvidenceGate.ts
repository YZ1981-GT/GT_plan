/**
 * useAiEvidenceGate — AI 证据门禁 / FormalOutput API composable（Wave 5/9 前端接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R8, R9, R10, R11
 * Design: §6.2 主要端点 (RAG/AI + FormalOutput)
 *
 * 后端路由（ai_evidence_gate_router）：
 *  - POST /ai/generations                        登记 AI 生成（ai.generate）
 *  - GET  /ai/generations/{id}                   查询状态
 *  - POST /ai/generations/{id}/confirm|revise|reject  人工确认/修订/拒绝
 *  - GET  /ai/generations/{id}/eligibility       FormalOutput 资格检查
 *  - POST /ai/formal-output/preflight|finalize   正式输出门禁
 *
 * Service Identity 不得确认（后端强制）。角色能力仅用于 UI 展示按钮启用态。
 */

import { ref, computed, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AiGenerationStatus {
  content_id: string
  entry_point: string
  model_name: string
  service_status: string
  output_hash: string
  lifecycle_status: string
  content_version: number
  created_at: string | null
}

export interface AiEligibilityReason {
  code: string
  description: string
  detail?: string | null
}

export interface AiEligibilityResult {
  content_id: string
  status: string
  eligible: boolean
  reasons: AiEligibilityReason[]
}

export interface FormalOutputEvaluation {
  phase: string
  verdict: string
  passed: boolean
  target_id: string
  target_type: string
  policy_version: string | null
  watermark: string | null
  evidence_count: number
  degraded: boolean
  blocking_reasons: Array<{
    code: string
    evidence_id?: string | null
    description: string
    detail?: string | null
  }>
}

/** 可执行 ai.confirm 的角色（人工确认；UI 展示用） */
const AI_CONFIRM_ROLES = new Set(['auditor', 'manager', 'partner', 'admin'])

// ─── Composable ──────────────────────────────────────────────────────────────

export function useAiEvidenceGate(
  projectId: Ref<string>,
  year: Ref<number>,
  userRole: Ref<string> | string,
) {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const _role = computed(() => (typeof userRole === 'string' ? userRole : userRole.value))
  const canConfirmAi = computed(() => AI_CONFIRM_ROLES.has(_role.value))

  const basePath = () =>
    `/api/projects/${projectId.value}/years/${year.value}/evidence/ai`

  async function getGeneration(contentId: string): Promise<AiGenerationStatus | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/generations/${contentId}`)
      return (res.data?.data ?? res.data) as AiGenerationStatus
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function confirmGeneration(contentId: string): Promise<any | null> {
    return _lifecycle('confirm', contentId)
  }

  async function reviseGeneration(contentId: string, newOutput: string): Promise<any | null> {
    return _lifecycle('revise', contentId, { new_output: newOutput })
  }

  async function rejectGeneration(contentId: string, reason: string): Promise<any | null> {
    return _lifecycle('reject', contentId, { reason })
  }

  async function _lifecycle(
    action: 'confirm' | 'revise' | 'reject',
    contentId: string,
    body?: Record<string, unknown>,
  ): Promise<any | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/generations/${contentId}/${action}`, body || {})
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function checkEligibility(contentId: string): Promise<AiEligibilityResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/generations/${contentId}/eligibility`)
      return (res.data?.data ?? res.data) as AiEligibilityResult
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function formalOutputPreflight(params: {
    target_id: string
    target_type: string
    policy_version?: string
  }): Promise<FormalOutputEvaluation | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/formal-output/preflight`, params)
      return (res.data?.data ?? res.data) as FormalOutputEvaluation
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function formalOutputFinalize(params: {
    target_id: string
    target_type: string
    preflight_watermark: string
    policy_version?: string
  }): Promise<FormalOutputEvaluation | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/formal-output/finalize`, params)
      return (res.data?.data ?? res.data) as FormalOutputEvaluation
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
    canConfirmAi,
    getGeneration,
    confirmGeneration,
    reviseGeneration,
    rejectGeneration,
    checkEligibility,
    formalOutputPreflight,
    formalOutputFinalize,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _extractError(e: any): string {
  const data = e?.response?.data
  const payload = data?.data || data
  if (payload?.error_code === 'SCOPE_NOT_FOUND_OR_FORBIDDEN') return '目标不可访问'
  if (payload?.error_code === 'EVIDENCE_GATE_BLOCKED') return payload.message || 'AI 证据门禁未通过'
  if (payload?.error_code) return payload.message || '操作失败'
  return e?.message || '网络错误'
}
