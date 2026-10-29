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
  workHourEntries as P_whe,
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

export interface WorkHourEntryRecord {
  id: string
  user_id: string
  project_id: string
  date: string
  hours: number
  cycle?: string
  wp_code?: string
  procedure?: string
  description?: string
  status: string
  submitted_at?: string
  approved_by?: string
  approved_at?: string
  rejected_reason?: string
  created_at?: string
  updated_at?: string
}

// ── Staff API ──

export async function listStaff(params?: {
  search?: string; department?: string; partner_name?: string; offset?: number; limit?: number
  title?: string; status?: string; project_id?: string
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

/** 删除人员时其仍在项目团队中（后端 409 `staff_has_assignments`，spec procedure-chain-hardening-and-java-contracts R12） */
export interface StaffHasAssignmentsDetail {
  error: 'staff_has_assignments'
  message: string
  projects: Array<{ project_id: string; project_name: string; roles: string[] }>
}

/** 错误是「人员仍在项目团队中」⇒ 返回后端给的项目清单与说明；否则 null（错误信封 `{code, message}` 里 message 是对象）。 */
export function staffHasAssignments(error: unknown): StaffHasAssignmentsDetail | null {
  const res = (error as { response?: { status?: number; data?: any } })?.response
  if (res?.status !== 409) return null
  const body = res.data?.message ?? res.data?.detail
  return body && typeof body === 'object' && body.error === 'staff_has_assignments' ? body : null
}

/**
 * 删除人员（仅 admin）。仍在项目团队中时后端 409 列出项目；用户确认后带 `revokeAssignments` 重试 ——
 * 同事务撤销其项目分配与项目成员行。调用方自管错误提示（`_silent`：不让全局拦截器先弹一次笼统提示）。
 */
export async function deleteStaff(id: string, opts: { revokeAssignments?: boolean } = {}) {
  const { data } = await http.delete(P.detail(id), {
    params: opts.revokeAssignments ? { revoke_assignments: true } : undefined,
    _silent: true,
  } as any)
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

// ── WorkHourEntry API (细粒度工时条目) ──

export async function listEntries(projectId: string, params?: {
  start_date?: string; end_date?: string; status?: string
}): Promise<WorkHourEntryRecord[]> {
  const { data } = await http.get(P_whe.list(projectId), { params })
  return (Array.isArray(data) ? data : data?.items || []) as WorkHourEntryRecord[]
}

export async function createEntry(projectId: string, payload: {
  date: string; hours: number; cycle?: string; wp_code?: string; procedure?: string; description?: string
}): Promise<WorkHourEntryRecord> {
  const { data } = await http.post(P_whe.create(projectId), payload)
  return data as WorkHourEntryRecord
}

export async function updateEntry(projectId: string, entryId: string, payload: {
  date?: string; hours?: number; cycle?: string; wp_code?: string; procedure?: string; description?: string
}): Promise<WorkHourEntryRecord> {
  const { data } = await http.put(P_whe.detail(projectId, entryId), payload)
  return data as WorkHourEntryRecord
}

export async function deleteEntry(projectId: string, entryId: string): Promise<void> {
  await http.delete(P_whe.detail(projectId, entryId))
}

export async function batchSubmitEntries(projectId: string, entryIds: string[]): Promise<{ submitted_count: number }> {
  const { data } = await http.post(P_whe.batchSubmit(projectId), { entry_ids: entryIds })
  return data as { submitted_count: number }
}

export async function getEntrySummary(projectId: string, params?: {
  period?: string
}): Promise<{ by_day: Record<string, number>; by_cycle: Record<string, number>; total: number }> {
  const { data } = await http.get(P_whe.summary(projectId), { params })
  return data as { by_day: Record<string, number>; by_cycle: Record<string, number>; total: number }
}
