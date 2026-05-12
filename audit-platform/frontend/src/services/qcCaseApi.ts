/**
 * 质控案例库 API
 */
import http from '@/utils/http'
import { qcCases as P, qcInspections as PI } from './apiPaths'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface QcCase {
  id: string
  title: string
  category: string
  severity: string
  description: string
  lessons_learned: string
  related_wp_refs: Array<Record<string, any>>
  related_standards: Array<{ code: string; section?: string; name?: string }>
  published_by: string
  published_at: string
  review_count: number
}

export interface QcCaseListResponse {
  items: QcCase[]
  total: number
}

export interface QcCaseListParams {
  category?: string
  severity?: string
  search?: string
  page?: number
  page_size?: number
}

export interface PublishAsCasePayload {
  title: string
  category: string
  severity: string
  lessons_learned?: string
}

// ─── API Paths ──────────────────────────────────────────────────────────────

// ─── API Functions ──────────────────────────────────────────────────────────

/** 获取案例列表（支持筛选和分页） */
export async function getCases(params?: QcCaseListParams): Promise<QcCaseListResponse> {
  const { data } = await http.get(P.list, { params })
  if (Array.isArray(data)) {
    return { items: data, total: data.length }
  }
  return data
}

/** 获取案例详情 */
export async function getCaseDetail(caseId: string): Promise<QcCase> {
  const { data } = await http.get(P.detail(caseId))
  return data
}

/** 从抽查项发布为案例 */
export async function publishAsCase(
  inspectionId: string,
  itemId: string,
  payload: PublishAsCasePayload,
): Promise<QcCase> {
  const { data } = await http.post(PI.publishAsCase(inspectionId, itemId), payload)
  return data
}
