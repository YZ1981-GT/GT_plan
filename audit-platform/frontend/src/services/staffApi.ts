/**
 * 人员库 + 团队委派 + 工时管理 API
 * Phase 9 Task 1.3/1.4/1.7
 */
import http from '@/utils/http'

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
  const { data } = await http.get('/api/staff', { params })
  const d = data.data ?? data
  return d as StaffListResponse
}

export async function createStaff(payload: Partial<StaffMember>): Promise<StaffMember> {
  const { data } = await http.post('/api/staff', payload)
  return (data.data ?? data) as StaffMember
}

export async function updateStaff(id: string, payload: Partial<StaffMember>): Promise<StaffMember> {
  const { data } = await http.put(`/api/staff/${id}`, payload)
  return (data.data ?? data) as StaffMember
}

export async function getStaffResume(id: string) {
  const { data } = await http.get(`/api/staff/${id}/resume`)
  return data.data ?? data
}

export async function getStaffProjects(id: string) {
  const { data } = await http.get(`/api/staff/${id}/projects`)
  return data.data ?? data
}


// ── Assignment API ──

export async function listAssignments(projectId: string): Promise<Assignment[]> {
  const { data } = await http.get(`/api/projects/${projectId}/assignments`)
  return (data.data ?? data) as Assignment[]
}

export async function saveAssignments(projectId: string, assignments: { staff_id: string; role: string; assigned_cycles?: string[] }[]) {
  const { data } = await http.post(`/api/projects/${projectId}/assignments`, { assignments })
  return data.data ?? data
}

export async function getMyAssignments() {
  const { data } = await http.get('/api/projects/my/assignments')
  return data.data ?? data
}

// ── WorkHour API ──

export async function listWorkHours(staffId: string, params?: { start_date?: string; end_date?: string }): Promise<WorkHourRecord[]> {
  const { data } = await http.get(`/api/staff/${staffId}/work-hours`, { params })
  return (data.data ?? data) as WorkHourRecord[]
}

export async function createWorkHour(staffId: string, payload: { project_id: string; work_date: string; hours: number; description?: string }) {
  const { data } = await http.post(`/api/staff/${staffId}/work-hours`, payload)
  return data.data ?? data
}

export async function updateWorkHour(hourId: string, payload: { hours?: number; description?: string; status?: string }) {
  const { data } = await http.put(`/api/work-hours/${hourId}`, payload)
  return data.data ?? data
}

export async function getAISuggestions(staffId: string, targetDate: string) {
  const { data } = await http.post('/api/work-hours/ai-suggest', null, { params: { staff_id: staffId, target_date: targetDate } })
  return data.data ?? data
}

export async function getProjectWorkHours(projectId: string) {
  const { data } = await http.get(`/api/projects/${projectId}/work-hours`)
  return data.data ?? data
}
