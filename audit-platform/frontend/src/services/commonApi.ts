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

// ── 知识库（全局+项目级） ──

export async function listKnowledgeLibraries(): Promise<any[]> {
  const { data } = await http.get('/api/knowledge/libraries')
  return Array.isArray(data) ? data : []
}

export async function listKnowledgeDocs(apiBase: string): Promise<any[]> {
  const { data } = await http.get(apiBase)
  return Array.isArray(data) ? data : data?.items || data?.documents || []
}

export async function uploadKnowledgeDoc(apiBase: string, formData: FormData): Promise<any> {
  const { data } = await http.post(apiBase, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function downloadKnowledgeDoc(apiBase: string, name: string): Promise<Blob> {
  const { data } = await http.get(`${apiBase}/${encodeURIComponent(name)}/download`, {
    responseType: 'blob',
  })
  return data
}

export async function deleteKnowledgeDoc(apiBase: string, name: string): Promise<void> {
  await http.delete(`${apiBase}/${encodeURIComponent(name)}`)
}

// ── 项目看板 ──

export async function getWorkpaperProgress(projectId: string): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/workpapers/progress`)
  return data
}

export async function getOverdueWorkpapers(projectId: string, days = 7): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/workpapers/overdue`, { params: { days } })
  return Array.isArray(data) ? data : []
}

export async function getProjectWorkHours(projectId: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/work-hours`)
  return Array.isArray(data) ? data : []
}


// ── T型账户 ──

export async function listTAccounts(projectId: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/t-accounts`)
  return Array.isArray(data) ? data : []
}

export async function getTAccount(projectId: string, id: string): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/t-accounts/${id}`)
  return data
}

export async function createTAccount(projectId: string, body: any): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/t-accounts`, body)
  return data
}

export async function addTAccountEntry(projectId: string, accountId: string, entry: any): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/t-accounts/${accountId}/entries`, entry)
  return data
}

export async function calculateTAccount(projectId: string, accountId: string): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/t-accounts/${accountId}/calculate`)
  return data
}

// ── 自定义模板 ──

export async function listCustomTemplates(params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get('/api/custom-templates', { params })
  return Array.isArray(data) ? data : []
}

export async function getCustomTemplate(id: string): Promise<any> {
  const { data } = await http.get(`/api/custom-templates/${id}`)
  return data
}

export async function createCustomTemplate(fd: FormData): Promise<any> {
  const { data } = await http.post('/api/custom-templates', fd)
  return data
}

export async function updateCustomTemplate(id: string, fd: FormData): Promise<any> {
  const { data } = await http.put(`/api/custom-templates/${id}`, fd)
  return data
}

export async function validateCustomTemplate(id: string): Promise<any> {
  const { data } = await http.post(`/api/custom-templates/${id}/validate`)
  return data
}

export async function publishCustomTemplate(id: string): Promise<void> {
  await http.post(`/api/custom-templates/${id}/publish`)
}

export async function copyCustomTemplate(id: string): Promise<void> {
  await http.post(`/api/custom-templates/${id}/copy`)
}

export async function deleteCustomTemplate(id: string): Promise<void> {
  await http.delete(`/api/custom-templates/${id}`)
}

// ── 监管备案 ──

export async function listFilings(params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get('/api/regulatory/filings', { params })
  return Array.isArray(data) ? data : []
}

export async function retryFiling(id: string): Promise<void> {
  await http.post(`/api/regulatory/filings/${id}/retry`)
}

// ── AI插件 ──

export async function listAIPlugins(): Promise<any[]> {
  const { data } = await http.get('/api/ai-plugins')
  return Array.isArray(data) ? data : []
}

// ── GT编码 ──

export async function listGTCoding(): Promise<any[]> {
  const { data } = await http.get('/api/gt-coding')
  return Array.isArray(data) ? data : []
}

// ── 复核对话 ──

export async function listReviewConversations(projectId: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/review-conversations`)
  return Array.isArray(data) ? data : []
}

// ── 穿透查询（移动端） ──

export async function getLedgerBalance(projectId: string, year: number): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/ledger/balance`, { params: { year } })
  return Array.isArray(data) ? data : []
}

export async function getLedgerEntries(projectId: string, code: string, year: number, page = 1, pageSize = 50): Promise<any> {
  const { data } = await http.get(
    `/api/projects/${projectId}/ledger/entries/${encodeURIComponent(code)}`,
    { params: { year, page, page_size: pageSize } },
  )
  return data
}

// ── 集团架构（合并页面） ──

export async function listChildProjects(parentProjectId: string): Promise<any[]> {
  const { data } = await http.get('/api/projects', { params: { parent_project_id: parentProjectId } })
  return Array.isArray(data) ? data : data?.items || []
}


// ── 管理看板 ──

export async function getDashboardOverview(): Promise<any> {
  const { data } = await http.get('/api/dashboard/overview')
  return data && typeof data === 'object' ? data : {}
}

export async function getDashboardProjectProgress(): Promise<any[]> {
  const { data } = await http.get('/api/dashboard/project-progress')
  return Array.isArray(data) ? data : []
}

export async function getDashboardStaffWorkload(): Promise<any[]> {
  const { data } = await http.get('/api/dashboard/staff-workload')
  return Array.isArray(data) ? data : []
}

export async function getDashboardRiskAlerts(): Promise<any[]> {
  const { data } = await http.get('/api/dashboard/risk-alerts')
  return Array.isArray(data) ? data : []
}

export async function getDashboardGroupProgress(): Promise<any[]> {
  const { data } = await http.get('/api/dashboard/group-progress')
  return Array.isArray(data) ? data : []
}

export async function getDashboardHoursHeatmap(): Promise<any[]> {
  const { data } = await http.get('/api/dashboard/hours-heatmap')
  return Array.isArray(data) ? data : []
}


// ── 批注 ──

export async function listWorkpaperAnnotations(projectId: string, objectType: string, objectId: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/annotations`, {
    params: { object_type: objectType, object_id: objectId },
  })
  return Array.isArray(data) ? data : []
}

export async function createAnnotation(projectId: string, body: any): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/annotations`, body)
  return data
}

export async function updateAnnotation(id: string, body: any): Promise<any> {
  const { data } = await http.put(`/api/annotations/${id}`, body)
  return data
}

export async function listAnnotations(projectId: string, filters?: { status?: string; priority?: string }): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/annotations`, { params: filters })
  return Array.isArray(data) ? data : (data?.data || [])
}

// ── 功能开关 ──

export async function checkFeatureFlag(flag: string, projectId?: string): Promise<boolean> {
  const { data } = await http.get(`/api/feature-flags/check/${flag}`, {
    params: projectId ? { project_id: projectId } : undefined,
    validateStatus: () => true,
  })
  return !!data?.enabled
}

export async function getFeatureMaturity(): Promise<Record<string, string>> {
  const { data } = await http.get('/api/feature-flags/maturity')
  return data && typeof data === 'object' ? data : {}
}

// ── 底稿提交复核 ──

export async function submitWorkpaperReview(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/working-papers/${wpId}/submit-review`)
  return data
}


// ══════════════════════════════════════════════════════════
// 以下从 enhancedApi.ts 迁移（Phase 7 增强功能）
// ══════════════════════════════════════════════════════════

// ── 过程记录 ──

export async function getEditHistory(projectId: string, wpId: string): Promise<any[]> {
  const { data } = await http.get(`/api/process-record/projects/${projectId}/workpapers/${wpId}/edit-history`)
  return Array.isArray(data) ? data : []
}

export async function getWpAttachments(projectId: string, wpId: string): Promise<any[]> {
  const { data } = await http.get(`/api/process-record/projects/${projectId}/workpapers/${wpId}/attachments`)
  return Array.isArray(data) ? data : []
}

export async function getAttachmentWorkpapers(attachmentId: string): Promise<any[]> {
  const { data } = await http.get(`/api/process-record/attachments/${attachmentId}/workpapers`)
  return Array.isArray(data) ? data : []
}

export async function linkAttachment(attachmentId: string, wpId: string): Promise<void> {
  await http.post('/api/process-record/link-attachment', { attachment_id: attachmentId, wp_id: wpId })
}

export async function getPendingAIContent(projectId: string, workpaperId?: string): Promise<any[]> {
  const params: Record<string, string> = {}
  if (workpaperId) params.workpaper_id = workpaperId
  const { data } = await http.get(`/api/process-record/projects/${projectId}/ai-content/pending`, { params })
  return Array.isArray(data) ? data : []
}

export async function confirmAIContent(contentId: string, status: string): Promise<void> {
  await http.put(`/api/process-record/ai-content/${contentId}/confirm`, { status })
}

export async function checkUnconfirmedAI(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.get(`/api/process-record/projects/${projectId}/workpapers/${wpId}/ai-check`)
  return data
}

// ── LLM 底稿对话 ──

export function wpChatSSE(wpId: string, message: string, context?: Record<string, any>) {
  return http.post(`/api/workpapers/${wpId}/ai/chat`, { message, context }, { responseType: 'stream' })
}

export async function generateLedgerAnalysis(projectId: string, body: { account_codes?: string[]; year?: number }): Promise<any> {
  const { data } = await http.post(`/api/workpapers/projects/${projectId}/ai/generate-ledger-analysis`, body)
  return data
}

// ── 抽样增强 ──

export interface AgingBracket { label: string; min_days: number; max_days: number | null }

export async function cutoffTest(projectId: string, body: {
  account_codes: string[]; year: number; days_before?: number; days_after?: number; amount_threshold?: number
}): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/sampling/cutoff-test`, body)
  return data
}

export async function agingAnalysis(projectId: string, body: {
  account_code: string; aging_brackets: AgingBracket[]; base_date: string; year?: number
}): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/sampling/aging-analysis`, body)
  return data
}

export async function monthlyDetail(projectId: string, body: { account_code: string; year: number }): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/sampling/monthly-detail`, body)
  return data
}

// ── 复核对话 ──

export interface ConversationItem {
  id: string; project_id: string; initiator_id: string; target_id: string
  related_object_type: string; status: string; title: string
  message_count?: number; created_at?: string; closed_at?: string
}

export async function createConversation(projectId: string, body: {
  target_id: string; related_object_type: string; related_object_id?: string; cell_ref?: string; title: string
}): Promise<any> {
  const { data } = await http.post(`/api/review-conversations?project_id=${projectId}`, body)
  return data
}

export async function listConversations(projectId: string, status?: string): Promise<any[]> {
  const params: Record<string, string> = { project_id: projectId }
  if (status) params.status = status
  const { data } = await http.get('/api/review-conversations', { params })
  return Array.isArray(data) ? data : []
}

export async function getMessages(conversationId: string): Promise<any[]> {
  const { data } = await http.get(`/api/review-conversations/${conversationId}/messages`)
  return Array.isArray(data) ? data : []
}

export async function sendMessage(conversationId: string, body: {
  content: string; message_type?: string; attachment_path?: string
}): Promise<any> {
  const { data } = await http.post(`/api/review-conversations/${conversationId}/messages`, body)
  return data
}

export async function closeConversation(conversationId: string): Promise<void> {
  await http.put(`/api/review-conversations/${conversationId}/close`)
}

export async function exportConversation(conversationId: string): Promise<any> {
  const { data } = await http.post(`/api/review-conversations/${conversationId}/export`)
  return data
}

// ── 论坛 ──

export interface ForumPostItem {
  id: string; author_id?: string; is_anonymous: boolean; category: string
  title: string; content: string; like_count: number; comment_count?: number; created_at?: string
}

export async function listPosts(category?: string): Promise<any[]> {
  const params: Record<string, string> = {}
  if (category) params.category = category
  const { data } = await http.get('/api/forum/posts', { params })
  return Array.isArray(data) ? data : data?.items || data?.posts || []
}

export async function createPost(body: { title: string; content: string; category?: string; is_anonymous?: boolean }): Promise<any> {
  const { data } = await http.post('/api/forum/posts', body)
  return data
}

export async function getComments(postId: string): Promise<any[]> {
  const { data } = await http.get(`/api/forum/posts/${postId}/comments`)
  return Array.isArray(data) ? data : data?.items || data?.comments || []
}

export async function createComment(postId: string, content: string): Promise<void> {
  await http.post(`/api/forum/posts/${postId}/comments`, { content })
}

export async function likePost(postId: string): Promise<void> {
  await http.post(`/api/forum/posts/${postId}/like`)
}

// ── 溯源 ──

export async function traceSection(projectId: string, sectionNumber: string): Promise<any> {
  const { data } = await http.get(`/api/report-review/${projectId}/trace/${encodeURIComponent(sectionNumber)}`)
  return data
}

export async function findingsSummary(projectId: string): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/findings-summary`)
  return data
}

// ── 打卡 ──

export async function checkIn(staffId: string, body: {
  latitude?: number; longitude?: number; location_name?: string; check_type?: string
}): Promise<void> {
  await http.post(`/api/staff/${staffId}/check-in`, body)
}

export async function listCheckIns(staffId: string): Promise<any[]> {
  const { data } = await http.get(`/api/staff/${staffId}/check-ins`)
  return Array.isArray(data) ? data : []
}

// ── 辅助余额汇总 ──

export async function auxSummary(projectId: string, year?: number): Promise<any[]> {
  const params: Record<string, any> = {}
  if (year) params.year = year
  const { data } = await http.get(`/api/projects/${projectId}/ledger/aux-summary`, { params })
  return Array.isArray(data) ? data : []
}

// ── 合并锁定 ──

export async function lockProject(projectId: string): Promise<void> {
  await http.post(`/api/consolidation/${projectId}/lock`)
}

export async function unlockProject(projectId: string): Promise<void> {
  await http.post(`/api/consolidation/${projectId}/unlock`)
}

export async function checkLockStatus(projectId: string): Promise<any> {
  const { data } = await http.get(`/api/consolidation/${projectId}/lock-status`)
  return data
}

// ── 快照 ──

export async function listSnapshots(projectId: string): Promise<any[]> {
  const { data } = await http.get(`/api/consolidation/${projectId}/snapshots`)
  return Array.isArray(data) ? data : []
}

export async function createSnapshot(projectId: string, year: number = 2025): Promise<void> {
  await http.post(`/api/consolidation/${projectId}/snapshots?year=${year}`)
}

// ── 推荐 ──

export async function recommendWorkpapers(projectId: string): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/ai/recommend-workpapers`)
  return data
}

// ── 差异报告 ──

export async function annualDiffReport(projectId: string): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/ai/annual-diff-report`)
  return data
}

// ── 附件分类 ──

export async function classifyAttachment(projectId: string, attachmentId: string, fileName: string): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/attachments/classify`, {
    attachment_id: attachmentId, file_name: fileName,
  })
  return data
}

// ── 排版模板 ──

export async function listFormatTemplates(): Promise<any[]> {
  const { data } = await http.get('/api/report-format-templates')
  return Array.isArray(data) ? data : []
}

export async function createFormatTemplate(body: {
  template_name: string; template_type: string; config: Record<string, any>
}): Promise<any> {
  const { data } = await http.post('/api/report-format-templates', body)
  return data
}

// ── 模板库三层体系 ──

export interface TemplateLibraryItem {
  id: string
  name: string
  type: string
  level: string
  level_label?: string
  wp_code?: string
  audit_cycle?: string
  report_scope?: string
  description?: string
  group_name?: string
  version?: string
  source_template_id?: string
}

export interface ProjectTemplateSelection {
  selection_id: string
  template_id: string
  template_name: string
  template_type: string
  level: string
  group_name?: string
  wp_code?: string
  report_scope?: string
  pulled_at?: string
  linked_trial_balance: boolean
  linked_adjustments: boolean
  linked_attachments: boolean
}

export async function getAvailableTemplates(params?: {
  template_type?: string
  group_id?: string
}): Promise<TemplateLibraryItem[]> {
  const { data } = await http.get('/api/template-library/available', { params })
  return Array.isArray(data) ? data : []
}

export async function listFirmTemplates(templateType?: string): Promise<TemplateLibraryItem[]> {
  const { data } = await http.get('/api/template-library/firm', {
    params: templateType ? { template_type: templateType } : undefined,
  })
  return Array.isArray(data) ? data : []
}

export async function createGroupTemplate(body: {
  source_template_id: string
  group_id: string
  group_name: string
}): Promise<{ id: string; name: string; message: string }> {
  const { data } = await http.post('/api/template-library/group', body)
  return data
}

export async function listGroupTemplates(groupId: string, templateType?: string): Promise<TemplateLibraryItem[]> {
  const { data } = await http.get(`/api/template-library/group/${groupId}`, {
    params: templateType ? { template_type: templateType } : undefined,
  })
  return Array.isArray(data) ? data : []
}

export async function selectTemplateForProject(projectId: string, templateId: string): Promise<{ selection_id: string }> {
  const { data } = await http.post(`/api/template-library/projects/${projectId}/select`, { template_id: templateId })
  return data
}

export async function getProjectTemplates(projectId: string): Promise<ProjectTemplateSelection[]> {
  const { data } = await http.get(`/api/template-library/projects/${projectId}/templates`)
  return Array.isArray(data) ? data : []
}

export async function pullTemplateToProject(projectId: string, templateId: string): Promise<{ template_name: string; target_path: string }> {
  const { data } = await http.post(`/api/template-library/projects/${projectId}/pull/${templateId}`)
  return data
}

export async function createCustomWorkpaper(projectId: string, body: {
  wp_code: string
  wp_name: string
  audit_cycle?: string
  year?: number
}): Promise<{ wp_id: string; wp_code: string; message: string }> {
  const { data } = await http.post(`/api/projects/${projectId}/working-papers/create-custom`, body)
  return data
}

// ── Excel↔HTML 互转 ──

export async function uploadExcelForParse(projectId: string, file: File): Promise<any> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await http.post(`/api/projects/${projectId}/excel-html/upload-parse`, fd)
  return data
}

export async function getExcelHtmlPreview(projectId: string, fileStem: string, sheetIndex = 0): Promise<{ html: string; version: number }> {
  const { data } = await http.get(`/api/projects/${projectId}/excel-html/preview/${fileStem}`, { params: { sheet_index: sheetIndex, editable: true } })
  return data
}

export async function saveExcelHtmlEdits(projectId: string, fileStem: string, edits: any[], sheetIndex = 0): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/excel-html/save-edits/${fileStem}`, { edits, sheet_index: sheetIndex })
  return data
}

export async function confirmExcelAsTemplate(projectId: string, fileStem: string, body: {
  template_name: string; template_type?: string; wp_code?: string; audit_cycle?: string
}): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/excel-html/confirm-template/${fileStem}`, body)
  return data
}

export async function syncFromOnlyoffice(projectId: string, fileStem: string): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/excel-html/sync-from-onlyoffice/${fileStem}`)
  return data
}

// ── 三形式联动统一模块接口 ──

export async function getModuleStructure(projectId: string, module: string, params?: Record<string, any>): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/excel-html/module/${module}/structure`, { params })
  return data
}

export async function getModuleHtml(projectId: string, module: string, params?: Record<string, any>): Promise<{ module: string; html: string }> {
  const { data } = await http.get(`/api/projects/${projectId}/excel-html/module/${module}/html`, { params })
  return data
}

export async function exportModuleExcel(projectId: string, module: string, params?: Record<string, any>): Promise<Blob> {
  const response = await http.post(`/api/projects/${projectId}/excel-html/module/${module}/export-excel`, null, {
    params,
    responseType: 'blob',
  })
  return response.data
}

export async function exportModuleWord(projectId: string, module: string, params?: Record<string, any>): Promise<Blob> {
  const response = await http.post(`/api/projects/${projectId}/excel-html/module/${module}/export-word`, null, {
    params,
    responseType: 'blob',
  })
  return response.data
}

// ── 四式联动：编辑锁 ──

export async function acquireEditLock(projectId: string, fileStem: string): Promise<{ locked: boolean }> {
  const { data } = await http.post(`/api/projects/${projectId}/excel-html/lock/${fileStem}`)
  return data
}

export async function releaseEditLock(projectId: string, fileStem: string): Promise<void> {
  await http.delete(`/api/projects/${projectId}/excel-html/lock/${fileStem}`)
}

export async function refreshEditLock(projectId: string, fileStem: string): Promise<void> {
  await http.put(`/api/projects/${projectId}/excel-html/lock/${fileStem}/refresh`)
}

// ── 四式联动：版本管理 ──

export async function listFileVersions(projectId: string, fileStem: string): Promise<any[]> {
  const { data } = await http.get(`/api/projects/${projectId}/excel-html/versions/${fileStem}`)
  return Array.isArray(data) ? data : []
}

export async function diffFileVersions(projectId: string, fileStem: string, v1: number, v2: number): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/excel-html/versions/${fileStem}/diff`, { params: { v1, v2 } })
  return data
}

export async function rollbackFileVersion(projectId: string, fileStem: string, version: number): Promise<any> {
  const { data } = await http.post(`/api/projects/${projectId}/excel-html/versions/${fileStem}/rollback/${version}`)
  return data
}

// ── 四式联动：公式执行 ──

export async function executeFormulas(projectId: string, fileStem: string, params?: { sheet_index?: number; year?: number }): Promise<{
  executed: number; total_formulas: number; errors: any[]; version: number
}> {
  const { data } = await http.post(`/api/projects/${projectId}/excel-html/execute-formulas/${fileStem}`, null, { params })
  return data
}

// ── 四式联动：单元格信息 ──

export async function getCellInfo(projectId: string, fileStem: string, cell: string): Promise<any> {
  const { data } = await http.get(`/api/projects/${projectId}/excel-html/cell-info/${fileStem}`, { params: { cell } })
  return data
}
