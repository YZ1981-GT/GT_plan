/**
 * D5 合并范围确认 API — 独立于 consolidationApi.ts（禁止修改）。
 *
 * 端点：
 *   GET  /api/consolidation/{project_id}/scope-confirmation/preview
 *   POST /api/consolidation/{project_id}/scope-confirmation/confirm
 */
import { api } from '@/services/apiProxy'

// ─── 类型 ───────────────────────────────────────────────────────────────────

export interface ScopeConfirmationNode {
  node_key: string
  role: string
  kind: string
  company_code: string
  company_name: string
  parent_node_key: string | null
  position: number
  relation: string | null
  consol_level: number
  flags: string[]
  via: string[]
  /** 只在 include_database_ids 时有值 */
  project_id?: string | null
  host_project_id?: string | null
}

export interface ScopeConfirmationDiagnostic {
  code: string
  message: string
  company_code?: string | null
  node_key?: string | null
  level?: string
}

export interface ScopeConfirmationPreview {
  project_id: string
  year: number
  report_scope: string
  revision: number
  fingerprint: string
  tree: Record<string, unknown>
  nodes: ScopeConfirmationNode[]
  diagnostics: ScopeConfirmationDiagnostic[]
  confirmed: boolean
  pending_legacy: boolean
  pending_confirmation: boolean
  can_confirm: boolean
  active_confirmation_id: string | null
}

export interface ConfirmScopeRequest {
  expected_fingerprint: string
  expected_revision: number
}

// ─── API ────────────────────────────────────────────────────────────────────

const basePath = (projectId: string) =>
  `/api/consolidation/${projectId}/scope-confirmation`

/** 只读预览：重建当前服务端树，返回指纹、revision 与确认状态。 */
export function previewScopeConfirmation(projectId: string) {
  return api.get<ScopeConfirmationPreview>(`${basePath(projectId)}/preview`)
}

/** 显式确认当前合并范围（CAS：fingerprint + revision 必须与服务端一致）。 */
export function confirmScope(projectId: string, body: ConfirmScopeRequest) {
  return api.post<ScopeConfirmationPreview>(`${basePath(projectId)}/confirm`, body)
}
