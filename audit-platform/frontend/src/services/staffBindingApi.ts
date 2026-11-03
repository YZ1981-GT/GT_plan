import http from '@/utils/http'
import { users as userPaths } from '@/services/apiPaths/system'
import { staff as staffPaths } from '@/services/apiPaths/collaboration'

/** 人员档案与登录账号的一条绑定（一个账号最多一份档案）。 */
export interface StaffBinding {
  user_id: string
  staff_id: string
  staff_name: string
  employee_no: string | null
  department: string | null
  status: string
}

export interface StaffBindingResult {
  user_id: string
  staff_id: string
  staff_name?: string
  employee_no?: string | null
  changed: boolean
  /** 绑定后对该账号生效的项目委派数量 */
  project_count?: number
  /** 为这些委派补建的项目成员行数量 */
  created_member_count?: number
}

/** 绑定弹窗的候选：未绑定账号的人员档案。 */
export interface UnboundStaffOption {
  id: string
  name: string
  employee_no?: string | null
  department?: string | null
  status?: string | null
}

export async function listStaffBindings(): Promise<StaffBinding[]> {
  const response = await http.get(userPaths.staffBindings.list)
  return Array.isArray(response.data) ? response.data : []
}

export async function bindStaffToUser(userId: string, staffId: string): Promise<StaffBindingResult> {
  const response = await http.post(userPaths.staffBindings.bind(userId), { staff_id: staffId })
  return response.data
}

export async function unbindStaffFromUser(userId: string, staffId: string): Promise<StaffBindingResult> {
  const response = await http.post(userPaths.staffBindings.unbind(userId), { staff_id: staffId })
  return response.data
}

/** 按姓名 / 工号搜索未绑定账号、未离职的人员档案。 */
export async function searchUnboundStaff(keyword: string): Promise<UnboundStaffOption[]> {
  const response = await http.get(staffPaths.list, {
    params: { search: keyword.trim() || undefined, unbound_only: true, limit: 20 },
  })
  const items = Array.isArray(response.data?.items) ? response.data.items : []
  return items.filter((item: UnboundStaffOption) => item.status !== 'resigned')
}
