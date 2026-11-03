/**
 * 企业树版本 API（原 D5 合并范围确认）— 独立于 consolidationApi.ts（禁止修改）。
 *
 * V206 起合并计算不再要求确认（spec consol-autotree-linkage-closure R1）：推送时自动记录版本，
 * 这里的 confirm 是可选的「手动记录为新版本」（CAS，记录方式 user）。
 *
 * 端点：
 *   GET  /api/consolidation/{project_id}/scope-confirmation/preview
 *   POST /api/consolidation/{project_id}/scope-confirmation/confirm
 */
import { api } from '@/services/apiProxy'
import type { ConsolTreeDiff } from '@/services/consolidationApi'

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
  /** 兼容旧字段：= matches_recorded */
  confirmed: boolean
  /** V206 起恒为 false（计算不需要确认） */
  pending_confirmation: boolean
  /** 未锁定才可手动记录 */
  can_confirm: boolean
  active_confirmation_id: string | null
  /** 当前树与已记录（active）版本一致 */
  matches_recorded: boolean
  /** 已记录版本号；0 = 尚未记录 */
  recorded_revision: number
  recorded_mode: 'user' | 'auto' | null
  recorded_at: string | null
  /** 与已记录版本相比有结构变化（改名不算） */
  structural_change: boolean
  diff: ConsolTreeDiff | null
}

export interface ConfirmScopeRequest {
  expected_fingerprint: string
  expected_revision: number
}

// ─── API ────────────────────────────────────────────────────────────────────

const basePath = (projectId: string) =>
  `/api/consolidation/${projectId}/scope-confirmation`

/**
 * 只读预览：重建当前服务端树，返回指纹、revision 与确认状态。
 * `opts.silent`：调用方自己处理失败（合并总览逐棵树读、失败只是不提示），不经全局拦截器弹错。
 */
export function previewScopeConfirmation(projectId: string, opts?: { silent?: boolean }) {
  const url = `${basePath(projectId)}/preview`
  return opts?.silent
    ? api.get<ScopeConfirmationPreview>(url, { _silent: true } as any)
    : api.get<ScopeConfirmationPreview>(url)
}

/** 手动把当前企业树记录为新版本（CAS：fingerprint + revision 必须与服务端一致）。 */
export function confirmScope(projectId: string, body: ConfirmScopeRequest) {
  return api.post<ScopeConfirmationPreview>(`${basePath(projectId)}/confirm`, body)
}
