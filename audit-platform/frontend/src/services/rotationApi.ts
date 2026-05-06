/**
 * 合伙人轮换检查 API — R1 需求 11
 */
import http from '@/utils/http'
import { rotation as R } from '@/services/apiPaths'

export interface RotationCheckResult {
  staff_id: string
  client_name: string
  continuous_years: number
  years_served: number[]
  next_rotation_due_year: number | null
  current_override_id: string | null
  rotation_limit: number
}

export interface RotationOverrideCreateParams {
  staff_id: string
  client_name: string
  original_years: number
  override_reason: string
}

export interface RotationOverrideResult {
  id: string
  staff_id: string
  client_name: string
  original_years: number
  override_reason: string
  approved_by_compliance_partner: string | null
  approved_by_chief_risk_partner: string | null
  override_expires_at: string | null
  created_at: string
}

/**
 * 检查指定人员对指定客户的连续审计年数
 */
export async function checkRotation(
  staffId: string,
  clientName: string,
): Promise<RotationCheckResult> {
  const { data } = await http.get(R.check, {
    params: { staff_id: staffId, client_name: clientName },
  })
  return data
}

/**
 * 创建轮换 override 申请（后端 stub）
 */
export async function createRotationOverride(
  params: RotationOverrideCreateParams,
): Promise<RotationOverrideResult> {
  const { data } = await http.post(R.overrides, params)
  return data
}
