/**
 * useLegalHoldGovernance — 法定保全与保留期清理 API composable（Wave 6/9 前端接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R2, R12, R13
 * Design: §6.2 主要端点 (Legal Hold)
 *
 * 后端路由（legal_hold_router）：
 *  - POST /legal-holds                 创建法定保全（legal_hold.create）
 *  - GET  /legal-holds                 列出本 scope 保全
 *  - GET  /legal-holds/{id}/scope      列出保全固化的 direct/transitive 范围
 *  - POST /legal-holds/{id}/release    解除保全（legal_hold.release）
 *  - POST /legal-holds/purge-jobs      清理任务（四条件门禁 retention.purge）
 */

import { ref, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LegalHoldItem {
  id: string
  project_id: string
  audit_year: number | null
  reason: string
  state: 'active' | 'released' | string
  graph_watermark: string | null
  release_reason: string | null
  released_by_user_id: string | null
  released_at: string | null
  created_at: string | null
}

export interface HoldScopeNode {
  node_type: string
  node_id: string
  scope_kind: string
  is_active: boolean
}

export interface PurgeResult {
  allowed: boolean
  delta: number
  unmet_conditions: string[]
  tombstone_id: string | null
  command_root_id?: string
}

export interface CreateHoldParams {
  reason: string
  seed_nodes?: Array<{ node_type: string; node_id: string }>
}

export interface PurgeJobParams {
  node_type: string
  node_id: string
  retention_expired?: boolean
  purge_reason?: string
  content_hash?: string
  retention_policy_version?: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useLegalHoldGovernance(projectId: Ref<string>, year: Ref<number>) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const holds = ref<LegalHoldItem[]>([])

  const basePath = () =>
    `/api/projects/${projectId.value}/years/${year.value}/evidence/legal-holds`

  async function listHolds(state?: 'active' | 'released', limit = 100): Promise<LegalHoldItem[]> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(basePath(), { params: { state, limit } })
      const data = res.data?.data ?? res.data
      holds.value = data?.items || []
      return holds.value
    } catch (e: any) {
      error.value = _extractError(e)
      holds.value = []
      return []
    } finally {
      loading.value = false
    }
  }

  async function createHold(params: CreateHoldParams): Promise<any | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(basePath(), params)
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function getHoldScope(
    holdId: string,
    scopeKind?: 'direct' | 'transitive',
    limit = 200,
  ): Promise<HoldScopeNode[]> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/${holdId}/scope`, {
        params: { scope_kind: scopeKind, limit },
      })
      const data = res.data?.data ?? res.data
      return data?.nodes || []
    } catch (e: any) {
      error.value = _extractError(e)
      return []
    } finally {
      loading.value = false
    }
  }

  async function releaseHold(holdId: string, reason: string): Promise<any | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/${holdId}/release`, { reason })
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function createPurgeJob(params: PurgeJobParams): Promise<PurgeResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/purge-jobs`, params)
      return (res.data?.data ?? res.data) as PurgeResult
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
    holds,
    listHolds,
    createHold,
    getHoldScope,
    releaseHold,
    createPurgeJob,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _extractError(e: any): string {
  const data = e?.response?.data
  const payload = data?.data || data
  if (payload?.error_code === 'SCOPE_NOT_FOUND_OR_FORBIDDEN') return '目标不可访问'
  if (payload?.error_code === 'LEGAL_HOLD_ACTIVE') return payload.message || '法定保全生效中，破坏性操作零效果'
  if (payload?.error_code) return payload.message || '操作失败'
  return e?.message || '网络错误'
}
