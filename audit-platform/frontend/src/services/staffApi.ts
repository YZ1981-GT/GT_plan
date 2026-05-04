/**
 * 人员库 + 团队委派 + 工时管理 API
 * Phase 9 Task 1.3/1.4/1.7
 *
 * 注意：http.ts 响应拦截器已自动解包 ApiResponse，
 * 所以 { data } = await http.get() 拿到的就是最终数据。
 */
import http from '@/utils/http'
import {
  staff as P, projects as P_proj, workHours as P_wh,
} from '@/services/apiPaths'

// ── Types ──

export interface StaffMember {
  id: string
  user_id?: string
  name: string
  employee_no?: string
  department?: string
  title?: string
  partner_name?: string
  partner_id?: string
  specialty?: string
  phone?: string
  email?: string
  source?: string  // seed / custom
  join_date?: string
  resume_data?: Record<string, any>
  created_at?: string
}

export interface StaffListResponse {
  items: StaffMember[]
  total: number
}

export interface Assignment {
  id: string
  project_id: string
  staff_id: string
  role: string
  assigned_cycles?: string[]
  assigned_at?: string
  staff_name?: string
  staff_title?: string
  employee_no?: string
  project_name?: string
}

export interface WorkHourRecord {
  id: string
  staff_id: string
  project_id: string
  project_name?: string
  work_date: string
  hours: number
  start_time?: string
  end_time?: string
  description?: string
  status: string
  ai_suggested: boolean
}

// ── Staff API ──

export async function listStaff(params?: {
  search?: string; department?: string; partner_name?: string; offset?: number; limit?: number
}): Promise<StaffListResponse> {
  const { data } = await http.get(P.list, { params })
  return data as StaffListResponse
}

export async function createStaff(payload: Partial<StaffMember>): Promise<StaffMember> {
  const { data } = await http.post(P.create, payload)
  return data as StaffMember
}

export async function updateStaff(id: string, payload: Partial<StaffMember>): Promise<StaffMember> {
  const { data } = await http.put(P.detail(id), payload)
  return data as StaffMember
}

export async function getStaffResume(id: string) {
  const { data } = await http.get(P.resume(id))
  return data
}

export async function deleteStaff(id: string) {
  const { data } = await http.delete(P.detail(id))
  return data
}

export async function getStaffProjects(id: string) {
  const { data } = await http.get(P.projects(id))
  return data
}

export async function getMyStaffId(): Promise<{ staff_id: string; name: string }> {
  const { data } = await http.get(P.meStaffId)
  return data as { staff_id: string; name: string }
}

// ── Assignment API ──

export async function listAssignments(projectId: string): Promise<Assignment[]> {
  const { data } = await http.get(P_proj.assignments(projectId))
  return (Array.isArray(data) ? data : data?.items || []) as Assignment[]
}

export async function saveAssignments(projectId: string, assignments: { staff_id: string; role: string; assigned_cycles?: string[] }[]) {
  const { data } = await http.post(P_proj.assignments(projectId), { assignments })
  return data
}

export async function getMyAssignments(): Promise<Assignment[]> {
  const { data } = await http.get(P_proj.myAssignments)
  return (Array.isArray(data) ? data : data?.items || []) as Assignment[]
}

// ── WorkHour API ──

export async function listWorkHours(staffId: string, params?: { start_date?: string; end_date?: string }): Promise<WorkHourRecord[]> {
  const { data } = await http.get(P.workHours(staffId), { params })
  return (Array.isArray(data) ? data : data?.items || []) as WorkHourRecord[]
}

export async function createWorkHour(staffId: string, payload: { project_id: string; work_date: string; hours: number; description?: string }) {
  const { data } = await http.post(P.workHours(staffId), payload)
  return data
}

export async function updateWorkHour(hourId: string, payload: { hours?: number; description?: string; status?: string }) {
  const { data } = await http.put(P_wh.detail(hourId), payload)
  return data
}

export async function getAISuggestions(staffId: string, targetDate: string) {
  const { data } = await http.post(P_wh.aiSuggest, null, { params: { staff_id: staffId, target_date: targetDate } })
  return data
}

export async function getProjectWorkHours(projectId: string) {
  const { data } = await http.get(P_proj.workHours(projectId))
  return data
}
