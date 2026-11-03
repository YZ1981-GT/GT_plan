/**
 * 签字流水线 API — R1 需求 4
 */
import http from '@/utils/http'
import { confirmationHeaders } from '@/utils/passwordConfirm'
import { signatures, projects as P_proj } from '@/services/apiPaths'
import type { GateReadinessData } from '@/components/gate/GateReadinessPanel.vue'

export interface WorkflowStep {
  id?: string
  order: number
  role: string
  required_user_id?: string | null
  status: 'waiting' | 'ready' | 'signed'
  signed_at?: string | null
  signed_by?: string | null
}

export interface SignDocumentParams {
  object_type: string
  object_id: string
  signer_id: string
  signature_level: string
  gate_eval_id?: string
  project_id?: string
  gate_type?: string
  required_order?: number
  required_role?: string
  prerequisite_signature_ids?: string[]
}

/**
 * 获取项目签字流水线
 */
export async function getSignatureWorkflow(projectId: string): Promise<WorkflowStep[]> {
  const { data } = await http.get(signatures.workflow(projectId))
  return data
}

/**
 * 执行签字（后端要求二次密码确认令牌；调用方先 `requestConfirmationToken()`，取消即不调用。
 * spec attachment-archive-and-a-class-evidence 需求 4.3：改造前不带令牌，签字恒 403）
 */
export async function signDocument(params: SignDocumentParams, confirmationToken: string): Promise<any> {
  const { data } = await http.post(signatures.sign, params, { headers: confirmationHeaders(confirmationToken) })
  return data
}

/**
 * 获取签字就绪检查（统一 schema）
 */
export async function getSignReadinessV2(projectId: string): Promise<GateReadinessData> {
  const { data } = await http.get(P_proj.signReadiness(projectId))
  return data
}
