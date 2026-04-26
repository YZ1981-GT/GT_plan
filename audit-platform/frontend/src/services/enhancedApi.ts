/**
 * Phase 10 API 服务层
 * 过程记录/LLM底稿对话/抽样增强/复核对话/批注/论坛/溯源/打卡/辅助汇总/合并增强/快照/推荐/差异/分类/排版
 *
 * 路径约定：
 *   - process_record 路由前缀: /api/process-record/projects/{id}/workpapers/...
 *   - wp_chat 路由前缀: /api/workpapers/{wp_id}/ai/...
 *   - 主底稿管理（workpaperApi.ts）: /api/projects/{id}/working-papers/...
 *   注意：workpapers 和 working-papers 两种路径并存，新代码统一用 working-papers
 */
import http from '@/utils/http'

// ── 过程记录 (Task 4) ────────────────────────────────────

export async function getEditHistory(projectId: string, wpId: string) {
  const r = await http.get(`/api/process-record/projects/${projectId}/workpapers/${wpId}/edit-history`)
  return r.data?.data ?? r.data ?? []
}

export async function getWpAttachments(projectId: string, wpId: string) {
  const r = await http.get(`/api/process-record/projects/${projectId}/workpapers/${wpId}/attachments`)
  return r.data?.data ?? r.data ?? []
}

export async function getAttachmentWorkpapers(attachmentId: string) {
  const r = await http.get(`/api/process-record/attachments/${attachmentId}/workpapers`)
  return r.data?.data ?? r.data ?? []
}

export async function linkAttachment(attachmentId: string, wpId: string) {
  return http.post('/api/process-record/link-attachment', { attachment_id: attachmentId, wp_id: wpId })
}

export async function getPendingAIContent(projectId: string, workpaperId?: string) {
  const params: Record<string, string> = {}
  if (workpaperId) params.workpaper_id = workpaperId
  const r = await http.get(`/api/process-record/projects/${projectId}/ai-content/pending`, { params })
  return r.data?.data ?? r.data ?? []
}

export async function confirmAIContent(contentId: string, status: string) {
  return http.put(`/api/process-record/ai-content/${contentId}/confirm`, { status })
}

export async function checkUnconfirmedAI(projectId: string, wpId: string) {
  const r = await http.get(`/api/process-record/projects/${projectId}/workpapers/${wpId}/ai-check`)
  return r.data?.data ?? r.data
}

// ── LLM 底稿对话 (Task 5) ────────────────────────────────

export function wpChatSSE(wpId: string, message: string, context?: Record<string, any>) {
  return http.post(`/api/workpapers/${wpId}/ai/chat`, { message, context }, { responseType: 'stream' })
}

export async function generateLedgerAnalysis(projectId: string, body: { account_codes?: string[]; year?: number }) {
  const r = await http.post(`/api/workpapers/projects/${projectId}/ai/generate-ledger-analysis`, body)
  return r.data?.data ?? r.data
}

// ── 抽样增强 (Task 6) ────────────────────────────────────

export interface AgingBracket { label: string; min_days: number; max_days: number | null }

export async function cutoffTest(projectId: string, body: {
  account_codes: string[]; year: number; days_before?: number; days_after?: number; amount_threshold?: number
}) {
  const r = await http.post(`/api/projects/${projectId}/sampling/cutoff-test`, body)
  return r.data?.data ?? r.data
}

export async function agingAnalysis(projectId: string, body: {
  account_code: string; aging_brackets: AgingBracket[]; base_date: string; year?: number
}) {
  const r = await http.post(`/api/projects/${projectId}/sampling/aging-analysis`, body)
  return r.data?.data ?? r.data
}

export async function monthlyDetail(projectId: string, body: { account_code: string; year: number }) {
  const r = await http.post(`/api/projects/${projectId}/sampling/monthly-detail`, body)
  return r.data?.data ?? r.data
}

// ── 复核对话 (Task 8) ────────────────────────────────────

export interface ConversationItem {
  id: string; project_id: string; initiator_id: string; target_id: string
  related_object_type: string; status: string; title: string
  message_count?: number; created_at?: string; closed_at?: string
}

export async function createConversation(projectId: string, body: {
  target_id: string; related_object_type: string; related_object_id?: string; cell_ref?: string; title: string
}) {
  const r = await http.post(`/api/review-conversations?project_id=${projectId}`, body)
  return r.data?.data ?? r.data
}

export async function listConversations(projectId: string, status?: string) {
  const params: Record<string, string> = { project_id: projectId }
  if (status) params.status = status
  const r = await http.get('/api/review-conversations', { params })
  return r.data?.data ?? r.data ?? []
}

export async function getMessages(conversationId: string) {
  const r = await http.get(`/api/review-conversations/${conversationId}/messages`)
  return r.data?.data ?? r.data ?? []
}

export async function sendMessage(conversationId: string, body: {
  content: string; message_type?: string; attachment_path?: string
}) {
  const r = await http.post(`/api/review-conversations/${conversationId}/messages`, body)
  return r.data?.data ?? r.data
}

export async function closeConversation(conversationId: string) {
  return http.put(`/api/review-conversations/${conversationId}/close`)
}

export async function exportConversation(conversationId: string) {
  const r = await http.post(`/api/review-conversations/${conversationId}/export`)
  return r.data?.data ?? r.data
}

// ── 批注 (Task 15) ───────────────────────────────────────

export interface AnnotationItem {
  id: string; object_type: string; object_id: string; cell_ref?: string
  content: string; priority: string; status: string; author_id: string
  created_at?: string
}

export async function createAnnotation(projectId: string, body: {
  object_type: string; object_id: string; cell_ref?: string; content: string
  priority?: string; mentioned_user_ids?: string[]
}) {
  const r = await http.post(`/api/projects/${projectId}/annotations`, body)
  return r.data?.data ?? r.data
}

export async function listAnnotations(projectId: string, params?: {
  object_type?: string; object_id?: string; status?: string; priority?: string
}) {
  const r = await http.get(`/api/projects/${projectId}/annotations`, { params })
  return r.data?.data ?? r.data ?? []
}

export async function updateAnnotation(annotationId: string, body: { status?: string; content?: string }) {
  return http.put(`/api/projects/annotations/${annotationId}`, body)
}

// ── 论坛 (Task 11) ──────────────────────────────────────

export interface ForumPostItem {
  id: string; author_id?: string; is_anonymous: boolean; category: string
  title: string; content: string; like_count: number; comment_count?: number; created_at?: string
}

export async function listPosts(category?: string) {
  const params: Record<string, string> = {}
  if (category) params.category = category
  const { data } = await http.get('/api/forum/posts', { params })
  return Array.isArray(data) ? data : data?.items || data?.posts || []
}

export async function createPost(body: { title: string; content: string; category?: string; is_anonymous?: boolean }) {
  const { data } = await http.post('/api/forum/posts', body)
  return data
}

export async function getComments(postId: string) {
  const { data } = await http.get(`/api/forum/posts/${postId}/comments`)
  return Array.isArray(data) ? data : data?.items || data?.comments || []
}

export async function createComment(postId: string, content: string) {
  return http.post(`/api/forum/posts/${postId}/comments`, { content })
}

export async function likePost(postId: string) {
  return http.post(`/api/forum/posts/${postId}/like`)
}

// ── 溯源 (Task 9) ───────────────────────────────────────

export async function traceSection(projectId: string, sectionNumber: string) {
  const r = await http.get(`/api/report-review/${projectId}/trace/${encodeURIComponent(sectionNumber)}`)
  return r.data?.data ?? r.data
}

export async function findingsSummary(projectId: string) {
  const r = await http.get(`/api/projects/${projectId}/findings-summary`)
  return r.data?.data ?? r.data
}

// ── 打卡 (Task 10) ──────────────────────────────────────

export async function checkIn(staffId: string, body: {
  latitude?: number; longitude?: number; location_name?: string; check_type?: string
}) {
  return http.post(`/api/staff/${staffId}/check-in`, body)
}

export async function listCheckIns(staffId: string) {
  const r = await http.get(`/api/staff/${staffId}/check-ins`)
  return r.data?.data ?? r.data ?? []
}

// ── 辅助余额汇总 (Task 13) ──────────────────────────────

export async function auxSummary(projectId: string, year?: number) {
  const params: Record<string, any> = {}
  if (year) params.year = year
  const r = await http.get(`/api/projects/${projectId}/ledger/aux-summary`, { params })
  return r.data?.data ?? r.data ?? []
}

// ── 合并锁定 (Task 7) ───────────────────────────────────

export async function lockProject(projectId: string) {
  return http.post(`/api/consolidation/${projectId}/lock`)
}

export async function unlockProject(projectId: string) {
  return http.post(`/api/consolidation/${projectId}/unlock`)
}

export async function checkLockStatus(projectId: string) {
  const r = await http.get(`/api/consolidation/${projectId}/lock-status`)
  return r.data?.data ?? r.data
}

// ── 快照 (Task 16) ──────────────────────────────────────

export async function listSnapshots(projectId: string) {
  const r = await http.get(`/api/consolidation/${projectId}/snapshots`)
  return r.data?.data ?? r.data ?? []
}

export async function createSnapshot(projectId: string, year: number = 2025) {
  return http.post(`/api/consolidation/${projectId}/snapshots?year=${year}`)
}

// ── 推荐 (Task 17) ──────────────────────────────────────

export async function recommendWorkpapers(projectId: string) {
  const r = await http.post(`/api/projects/${projectId}/ai/recommend-workpapers`)
  return r.data?.data ?? r.data
}

// ── 差异报告 (Task 19) ──────────────────────────────────

export async function annualDiffReport(projectId: string) {
  const r = await http.post(`/api/projects/${projectId}/ai/annual-diff-report`)
  return r.data?.data ?? r.data
}

// ── 附件分类 (Task 20) ──────────────────────────────────

export async function classifyAttachment(projectId: string, attachmentId: string, fileName: string) {
  const r = await http.post(`/api/projects/${projectId}/attachments/classify`, {
    attachment_id: attachmentId, file_name: fileName,
  })
  return r.data?.data ?? r.data
}

// ── 排版模板 (Task 21) ──────────────────────────────────

export async function listFormatTemplates() {
  const r = await http.get('/api/report-format-templates')
  return r.data?.data ?? r.data ?? []
}

export async function createFormatTemplate(body: {
  template_name: string; template_type: string; config: Record<string, any>
}) {
  return http.post('/api/report-format-templates', body)
}
