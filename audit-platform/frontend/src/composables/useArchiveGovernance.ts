/**
 * useArchiveGovernance — 归档清单与离线校验 API composable（Wave 6/9 前端接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R11, R15
 * Design: §6.2 主要端点 (Archive)
 *
 * 后端路由（archive_manifest_router）：
 *  - POST /archive/preflight              归档前置门禁（冻结 watermark，不落库）
 *  - POST /archive/manifests              构建/封存归档清单（archive.seal）
 *  - GET  /archive/manifests              列出本 scope 清单
 *  - GET  /archive/manifests/{id}         清单详情（entries/edges + 阻断报告）
 *  - POST /archive/verify                 离线校验封存包（独立重算 hash）
 */

import { ref, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ArchivePreflightResult {
  watermark: string | null
  policy_version: string | null
  phase: string
  evidence_ready: boolean
}

export interface ArchiveManifestSummary {
  id: string
  version_no: number
  watermark: string | null
  policy_version: string | null
  package_hash: string | null
  state: string
  has_blocking_report: boolean
  sealed_at: string | null
  created_at: string | null
}

export interface ArchiveManifestDetail {
  id: string
  version_no: number
  watermark: string | null
  policy_version: string | null
  package_hash: string | null
  state: string
  blocking_difference_report: Record<string, unknown> | null
  sealed_at: string | null
  entries: Array<{
    node_type: string
    node_id: string
    node_version: number | null
    node_hash: string | null
    node_state: string | null
  }>
  edges: Array<{
    source_type: string
    source_id: string
    target_type: string
    target_id: string
    relation: string | null
    edge_hash: string | null
  }>
}

export interface ArchiveBuildResult {
  success?: boolean
  manifest_id?: string
  version?: number
  state?: string
  package_hash?: string
  sealed_package?: Record<string, unknown>
  blocked?: boolean
  blocking_difference_report?: Record<string, unknown>
  command_root_id?: string
  replayed?: boolean
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useArchiveGovernance(projectId: Ref<string>, year: Ref<number>) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const manifests = ref<ArchiveManifestSummary[]>([])

  const basePath = () =>
    `/api/projects/${projectId.value}/years/${year.value}/evidence/archive`

  async function preflight(policyVersion?: string): Promise<ArchivePreflightResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/preflight`, { policy_version: policyVersion })
      return (res.data?.data ?? res.data) as ArchivePreflightResult
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function buildManifest(policyVersion?: string): Promise<ArchiveBuildResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/manifests`, { policy_version: policyVersion })
      return (res.data?.data ?? res.data) as ArchiveBuildResult
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function listManifests(limit = 100): Promise<ArchiveManifestSummary[]> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/manifests`, { params: { limit } })
      const data = res.data?.data ?? res.data
      manifests.value = data?.items || []
      return manifests.value
    } catch (e: any) {
      error.value = _extractError(e)
      manifests.value = []
      return []
    } finally {
      loading.value = false
    }
  }

  async function getManifest(manifestId: string): Promise<ArchiveManifestDetail | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/manifests/${manifestId}`)
      return (res.data?.data ?? res.data) as ArchiveManifestDetail
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function verifyPackage(pkg: Record<string, unknown>): Promise<Record<string, unknown> | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.post(`${basePath()}/verify`, { package: pkg })
      return (res.data?.data ?? res.data) as Record<string, unknown>
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
    manifests,
    preflight,
    buildManifest,
    listManifests,
    getManifest,
    verifyPackage,
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
