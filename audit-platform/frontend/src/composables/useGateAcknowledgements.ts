/**
 * S2 ADR-CCN-06: 门禁逐项确认留痕 — 前端 composable
 *
 * 提供确认列表、新建确认、撤销确认三个 API 函数。
 */
import { api } from '@/services/apiProxy'

export interface GateAcknowledgement {
  id: string
  project_id: string
  year: number
  check_name: string
  branch_id: string
  status: string
  result_fingerprint: string
  reason: string
  acknowledged_by: string
  acknowledged_role: string
  created_at: string | null
  revoked_at: string | null
  revoked_by: string | null
}

export interface AcknowledgeBody {
  year: number
  check_name: string
  branch_id?: string
  status: string
  key_numbers?: Record<string, number | null>
  reason: string
}

/**
 * 列出项目 + 年度的全部确认记录
 */
export async function listAcks(
  projectId: string,
  year: number,
): Promise<GateAcknowledgement[]> {
  return api.get(
    `/api/projects/${projectId}/consistency-gate/acknowledgements?year=${year}`,
  )
}

/**
 * 新建确认
 */
export async function acknowledge(
  projectId: string,
  body: AcknowledgeBody,
): Promise<GateAcknowledgement> {
  return api.post(
    `/api/projects/${projectId}/consistency-gate/acknowledgements`,
    body,
  )
}

/**
 * 撤销确认
 */
export async function revoke(
  projectId: string,
  ackId: string,
): Promise<{ id: string; revoked_at: string; revoked_by: string }> {
  return api.post(
    `/api/projects/${projectId}/consistency-gate/acknowledgements/${ackId}/revoke`,
  )
}
