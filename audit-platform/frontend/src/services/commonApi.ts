/**
 * 通用 API 服务 — 覆盖各页面直接 http 调用的端点
 * 规则：所有页面必须通过 API 服务层调用，不允许直接拼 URL
 */
import http from '@/utils/http'

// ── 项目 ──

export async function listProjects(params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get('/api/projects', { params })
  return Array.isArray(data) ? data : data?.items || []
}

export async function getProjectWizardState(projectId: string): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/wizard`)
  return data
}

// ── 人员 ──

export async function getMyStaffId(): Promise<string | null> {
  const { data } = await http.get('/api/staff/me/staff-id', { validateStatus: () => true })
  return data?.staff_id || data?.data?.staff_id || null
}

export async function getMyAssignments(): Promise<any[]> {
  const { data } = await http.get('/api/staff/my/assignments', { validateStatus: () => true })
  return Array.isArray(data) ? data : data?.data || []
}

export async function getMyTodos(): Promise<any[]> {
  const { data } = await http.get('/api/staff/me/todos', { validateStatus: () => true })
  return Array.isArray(data) ? data : data?.items || []
}

export async function searchStaff(query: string, limit = 20): Promise<any[]> {
  const { data } = await http.get('/api/staff', { params: { search: query, limit } })
  return data?.items || (Array.isArray(data) ? data : [])
}

// ── 审计程序 ──

export async function getProcedures(projectId: string, cycle: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/procedures/${cycle}`, { validateStatus: () => true })
  return Array.isArray(data) ? data : data?.data || []
}

export async function updateProcedureTrim(projectId: string, cycle: string, items: any[]): Promise<void> {
  await http.put(`/api/projects/${projectId}/procedures/${cycle}/trim`, { items })
}

/** 聚合端点：一次获取当前用户所有被委派的程序（避免逐循环请求） */
export async function getMyProcedureTasks(staffId: string): Promise<any[]> {
  // 后端暂无聚合端点，先用前端聚合（后续优化为后端聚合）
  const assignments = await getMyAssignments()
  const CYCLES = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','S','Q']
  const allTasks: any[] = []
  for (const proj of assignments) {
    const pid = proj.project_id
    for (const cycle of CYCLES) {
      try {
        const procs = await getProcedures(pid, cycle)
        const myProcs = procs.filter((p: any) => p.status === 'execute' && p.assigned_to === staffId)
        for (const p of myProcs) {
          allTasks.push({ ...p, project_id: pid, project_name: proj.project_name || proj.client_name })
        }
      } catch { /* 项目可能没有初始化程序 */ }
    }
  }
  return allTasks
}

// ── 看板 ──

export async function getDashboardProjectStaffHours(projectId: string): Promise<any> {
  const { data } = await http.get('/api/dashboard/project-staff-hours', { params: { project_id: projectId } })
  return data
}

export async function getDashboardStaffDetail(staffId: string): Promise<any> {
  const { data } = await http.get('/api/dashboard/staff-detail', { params: { staff_id: staffId } })
  return data
}

export async function getDashboardAvailableStaff(maxHours: number): Promise<any> {
  const { data } = await http.get('/api/dashboard/available-staff', { params: { max_hours: maxHours } })
  return data
}

// ── 一致性检查 ──

export async function runConsistencyCheck(projectId: string, year = 2025): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/consistency-check/run`, null, { params: { year } })
  return data
}

export async function getConsistencyCheck(projectId: string, year = 2025): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/consistency-check`, { params: { year } })
  return data
}

// ── 附注 ──

export async function refreshDisclosureFromWorkpapers(projectId: string, year: number): Promise<void> {
  await http.post(`/api/disclosure-notes/${projectId}/${year}/refresh-from-workpapers`)
}

// ── 期后事项 ──

export async function listSubsequentEvents(projectId: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/subsequent-events`)
  return Array.isArray(data) ? data : []
}

export async function createSubsequentEvent(projectId: string, body: any): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/subsequent-events`, body)
  return data
}

// ── 用户管理 ──

export async function listUsers(): Promise<any[]> {
  const { data } = await http.get('/api/users')
  return Array.isArray(data) ? data : []
}

export async function createUser(body: any): Promise<any> {
  const { data } = await http.post('/api/users', body)
  return data
}

export async function updateUser(userId: string, body: any): Promise<any> {
  const { data } = await http.put(`/api/users/${userId}`, body)
  return data
}

// ── 系统设置 ──

export async function getSystemSettings(): Promise<any> {
  const { data } = await http.get('/api/settings')
  return data
}

export async function updateSystemSetting(key: string, value: any): Promise<any> {
  const { data } = await http.put('/api/settings', { updates: { [key]: value } })
  return data
}

export async function getSystemHealth(): Promise<any> {
  const { data } = await http.get('/api/settings/health')
  return data
}

// ── 私人库 ──

export async function listPrivateFiles(userId: string): Promise<any[]> {
  const { data } = await http.get(`/api/users/${userId}/private-storage`)
  return Array.isArray(data) ? data : data?.files || []
}

export async function getPrivateQuota(userId: string): Promise<any> {
  const { data } = await http.get(`/api/users/${userId}/private-storage/quota`)
  return data
}

export async function uploadPrivateFile(userId: string, formData: FormData): Promise<void> {
  await http.post(`/api/users/${userId}/private-storage/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export async function downloadPrivateFile(userId: string, name: string): Promise<Blob> {
  const { data } = await http.get(`/api/users/${userId}/private-storage/${name}/download`, {
    responseType: 'blob',
  })
  return data
}

export async function deletePrivateFile(userId: string, name: string): Promise<void> {
  await http.delete(`/api/users/${userId}/private-storage/${name}`)
}

// ── 文件下载工具（解决 window.open 不带 Authorization 头的问题） ──

export async function downloadFileAsBlob(url: string, filename: string): Promise<void> {
  const response = await http.get(url, { responseType: 'blob' })
  const blob = new Blob([response.data])
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}


// ── 回收站 ──

export async function getRecycleBinStats(): Promise<any> {
  const { data } = await http.get('/api/recycle-bin/stats')
  return data
}

export async function listRecycleBinItems(params?: Record<string, any>): Promise<{ items: any[]; total: number }> {
  const { data } = await http.get('/api/recycle-bin', { params })
  return { items: data?.items || [], total: data?.total || 0 }
}

export async function restoreRecycleBinItem(itemId: string): Promise<any> {
  const { data } = await http.post(`/api/recycle-bin/${itemId}/restore`)
  return data
}

export async function permanentDeleteItem(itemId: string): Promise<any> {
  const { data } = await http.delete(`/api/recycle-bin/${itemId}`)
  return data
}

export async function emptyRecycleBin(): Promise<any> {
  const { data } = await http.post('/api/recycle-bin/empty')
  return data
}

// ── 知识库 ──

export async function listKnowledgeDocuments(category: string, params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get(`/api/knowledge/${category}`, { params })
  return Array.isArray(data) ? data : data?.documents || []
}

export async function uploadKnowledgeDocument(category: string, formData: FormData): Promise<any> {
  const { data } = await http.post(`/api/knowledge/${category}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function deleteKnowledgeDocument(category: string, docId: string): Promise<void> {
  await http.delete(`/api/knowledge/${category}/${docId}`)
}

export async function searchKnowledge(query: string): Promise<any[]> {
  const { data } = await http.get('/api/knowledge/search', { params: { q: query } })
  return Array.isArray(data) ? data : data?.results || []
}

export async function listProjectKnowledge(projectId: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/knowledge`)
  return Array.isArray(data) ? data : data?.documents || []
}

// ── 性能监控 ──

export async function getPerformanceStats(): Promise<any> {
  const { data } = await http.get('/api/admin/performance-stats')
  return data
}

export async function getSlowQueries(): Promise<any[]> {
  const { data } = await http.get('/api/admin/slow-queries')
  return data?.queries || []
}

export async function getPerformanceMetrics(hours = 24): Promise<any> {
  const { data } = await http.get('/api/admin/performance-metrics', { params: { hours } })
  return data
}

// ── 注册 ──

export async function registerUser(body: { username: string; email: string; password: string }): Promise<any> {
  const { data } = await http.post('/api/auth/register', body)
  return data
}

// ── 附件管理 ──

export async function listAttachments(projectId: string, params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/attachments`, { params })
  return Array.isArray(data) ? data : data?.items || []
}

export async function searchAttachments(projectId: string, query: string): Promise<any[]> {
  const { data } = await http.get('/api/attachments/search', { params: { project_id: projectId, q: query } })
  return Array.isArray(data) ? data : []
}

export async function uploadAttachment(projectId: string, formData: FormData): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/attachments/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ── 审计程序裁剪 ──

export async function initProcedures(projectId: string, cycle: string): Promise<any[]> {
  const { data } = await http.post(`/api/projects/${projectId}/procedures/${cycle}/init`)
  return data?.procedures || (Array.isArray(data) ? data : [])
}

export async function addCustomProcedure(projectId: string, cycle: string, body: any): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/procedures/${cycle}/custom`, body)
  return data
}

export async function applyProcedureScheme(projectId: string, cycle: string, sourceProjectId: string): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/procedures/${cycle}/apply-scheme`, null, {
    params: { source_project_id: sourceProjectId },
  })
  return data
}
