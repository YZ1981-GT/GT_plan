/**
 * useEvidenceRefs — 证据关系查询 composable（Task 4.4, Wave 3）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R2, R3, R4
 * Design: §6.2 主要端点 (EvidenceRef)
 *
 * 提供：
 *  - 双向查询（source→refs / evidence→refs）
 *  - 单个 ref 详情
 *  - 影响路径查询
 *  - 创建/停用引用
 *  - 脱敏错误处理（跨项目显示 "目标不可访问"）
 */

import { ref, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface EvidenceRefItem {
  id: string
  project_id: string
  audit_year: number
  source_type: string
  source_id: string
  source_version: number | null
  evidence_type: string
  evidence_id: string
  attachment_version_id: string | null
  target_version: number | null
  target_hash: string | null
  label: string | null
  context: string | null
  intent_hash: string
  status: string
  created_at: string
}

export interface EvidenceRefsPage {
  items: EvidenceRefItem[]
  next_cursor: string | null
  has_more: boolean
}

export interface ImpactNode {
  target_type: string
  target_id: string
  distance: number
  path: string[]
}

export interface ImpactResult {
  nodes: ImpactNode[]
  total_visited: number
  truncated: boolean
}

export interface CreateRefParams {
  source_type: string
  source_id: string
  source_version?: number
  evidence_type: string
  evidence_id: string
  attachment_version_id?: string
  target_version?: number
  target_hash?: string
  label?: string
  context?: string
}

export interface DeactivateResult {
  ref_id: string
  previous_status: string
  new_status: string
  reason: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useEvidenceRefs(projectId: Ref<string>, year: Ref<number>) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const refs = ref<EvidenceRefItem[]>([])
  const hasMore = ref(false)
  const nextCursor = ref<string | null>(null)

  const basePath = () =>
    `/api/projects/${projectId.value}/years/${year.value}/evidence/refs`

  /**
   * 查询 EvidenceRef 列表（双向：source / evidence 方向）
   */
  async function queryRefs(params: {
    direction?: 'source' | 'evidence'
    source_type?: string
    source_id?: string
    evidence_type?: string
    evidence_id?: string
    status?: 'active' | 'inactive'
    cursor?: string
    limit?: number
  }): Promise<EvidenceRefsPage | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/references`, { params })
      const data = res.data?.data || res.data
      refs.value = data.items || []
      nextCursor.value = data.next_cursor || null
      hasMore.value = data.has_more || false
      return data as EvidenceRefsPage
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取单个 EvidenceRef 详情
   */
  async function getRef(refId: string): Promise<EvidenceRefItem | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/references/${refId}`)
      return (res.data?.data || res.data) as EvidenceRefItem
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 查询影响路径（R4.4: 直接 + 传递引用，去重且仅含可读对象）
   */
  async function queryImpact(params: {
    source_type: string
    source_id: string
    max_depth?: number
    limit?: number
  }): Promise<ImpactResult | null> {
    loading.value = true
    error.value = null
    try {
      const res = await http.get(`${basePath()}/impact`, { params })
      return (res.data?.data || res.data) as ImpactResult
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 创建 EvidenceRef（R3.1）
   */
  async function createRef(
    params: CreateRefParams,
    idempotencyKey?: string
  ): Promise<{ id: string; status: string; created: boolean } | null> {
    loading.value = true
    error.value = null
    try {
      const headers: Record<string, string> = {}
      if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
      const res = await http.post(`${basePath()}/references`, params, { headers })
      return res.data?.data || res.data
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 停用 EvidenceRef（R3.4）
   */
  async function deactivateRef(
    refId: string,
    reason: string,
    idempotencyKey?: string
  ): Promise<DeactivateResult | null> {
    loading.value = true
    error.value = null
    try {
      const headers: Record<string, string> = {}
      if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
      const res = await http.post(
        `${basePath()}/references/${refId}/deactivate`,
        { reason },
        { headers }
      )
      return (res.data?.data || res.data) as DeactivateResult
    } catch (e: any) {
      error.value = _extractError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    // state
    loading,
    error,
    refs,
    hasMore,
    nextCursor,
    // methods
    queryRefs,
    getRef,
    queryImpact,
    createRef,
    deactivateRef,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 提取脱敏错误消息（R4.2: 跨项目错误显示通用 "目标不可访问"）
 */
function _extractError(e: any): string {
  const data = e?.response?.data
  // ResponseWrapperMiddleware 包装的 data.data 或直接 data
  const payload = data?.data || data
  if (payload?.error_code === 'SCOPE_NOT_FOUND_OR_FORBIDDEN') {
    return '目标不可访问'
  }
  if (payload?.error_code === 'METADATA_INCOMPLETE') {
    return '元数据不完整，请先补充附件证据属性'
  }
  if (payload?.error_code) {
    return payload.message || '操作失败'
  }
  return e?.message || '网络错误'
}
