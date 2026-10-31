import http from '@/utils/http'
import { users as userPaths } from '@/services/apiPaths/system'

export interface ProjectCreationGrant {
  id: string
  manager_user_id: string
  manager_username: string
  company_code: string
  valid_from: string
  valid_until: string | null
  version: number
  source: string
  reason: string
  granted_by: string | null
  granted_by_username: string
  /** suspended：账号已停用、删除或不再是现场经理，授权门不会放行。 */
  status: 'active' | 'expired' | 'suspended'
  created_at: string | null
}

export interface GrantProjectCreationRequest {
  company_codes: string[]
  valid_until?: string | null
  reason: string
}

export async function listProjectCreationGrants(
  managerUserId?: string,
): Promise<ProjectCreationGrant[]> {
  const response = await http.get(userPaths.projectCreationGrants.list, {
    params: managerUserId ? { manager_user_id: managerUserId } : undefined,
  })
  return Array.isArray(response.data) ? response.data : []
}

export async function grantProjectCreation(
  managerUserId: string,
  body: GrantProjectCreationRequest,
): Promise<ProjectCreationGrant[]> {
  const response = await http.post(userPaths.projectCreationGrants.grant(managerUserId), body)
  return Array.isArray(response.data) ? response.data : []
}

/**
 * 建项被拒（403）时给用户看的原因。后端会说明哪里不满足（如「有 1 个企业代码暂无建项授权，请联系管理员授权」），
 * 且只涉及用户自己提交的代码；全局拦截器对 403 只显示「权限不足」，所以建项入口改用这里的文字。
 */
export function creationDeniedMessage(error: any): string {
  const detail = error?.response?.data?.detail ?? error?.response?.data?.message
  const text = typeof detail === 'string' ? detail : detail?.message
  // 兜底不点名「企业代码」：没带原因的 403 也可能来自来源项目权限等其他门禁
  return typeof text === 'string' && text.trim()
    ? text.trim()
    : '没有建项权限，请联系管理员'
}

export async function revokeProjectCreationGrant(
  grantId: string,
  expectedVersion: number,
  reason: string,
): Promise<{ id: string; revoked: boolean }> {
  const response = await http.post(userPaths.projectCreationGrants.revoke(grantId), {
    expected_version: expectedVersion,
    reason,
  })
  return response.data
}
