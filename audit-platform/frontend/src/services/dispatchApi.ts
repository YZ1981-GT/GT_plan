/**
 * 分发记录 API 封装 — D0-1 跨底稿分发持久化
 *
 * Feature: cross-workpaper-dispatch-persistence
 * 端点: /api/projects/{projectId}/dispatch-records
 */
import { api } from '@/services/apiProxy'

// ─── 类型定义 ────────────────────────────────────────────────────────────────

export type DispatchTarget = 'D0-4' | 'D0-5' | 'D0-6' | 'D0-7'

export interface DispatchEntry {
  confirm_index: string
  target: DispatchTarget
  entity_name?: string
  account_type?: string
  amount?: number
  reason?: string
}

export interface DispatchRecord {
  id: string
  project_id: string
  confirm_index: string
  target: DispatchTarget
  entity_name: string | null
  account_type: string | null
  amount: number | null
  reason: string | null
  dispatched_by: string
  dispatched_at: string
}

export interface BatchDispatchResponse {
  dispatched: DispatchRecord[]
  skipped: { confirm_index: string; target: string; reason: string }[]
}

export interface ListDispatchResponse {
  items: DispatchRecord[]
  total: number
}

// ─── API 方法 ────────────────────────────────────────────────────────────────

const BASE = (projectId: string) => `/api/projects/${projectId}/dispatch-records`

export const dispatchApi = {
  /** 批量创建分发记录（去重） */
  batchCreate: (projectId: string, entries: DispatchEntry[]): Promise<BatchDispatchResponse> =>
    api.post(BASE(projectId), { entries }),

  /** 查询分发记录（可选过滤） */
  list: (
    projectId: string,
    params?: { target?: string; confirm_index?: string },
  ): Promise<ListDispatchResponse> =>
    api.get(BASE(projectId), { params }),

  /** 撤回单条分发记录 */
  revoke: (projectId: string, recordId: string): Promise<{ detail: string; id: string }> =>
    api.delete(`${BASE(projectId)}/${recordId}`),
}
