/**
 * 项目经理视角 API 服务
 * 待复核收件箱 / 批量复核 / 进度看板 / 进度简报 / 交叉引用 / 客户沟通 / 调整汇总导出
 */
import http from '@/utils/http'
import { reviews as P_rev, adjustments as P_adj, projects as P_proj } from '@/services/apiPaths'

// ── Types ──

export interface ReviewInboxItem {
  id: string
  project_id: string
  project_name: string
  wp_code: string
  wp_name: string
  audit_cycle: string
  status: string
  review_status: string
  assigned_to: string | null
  submitted_at: string | null
  file_version: number
  conversation_id: string | null
  conversation_message_count: number
}

export interface ReviewInboxResult {
  items: ReviewInboxItem[]
  total: number
  page: number
  page_size: number
}

export interface BatchReviewResult {
  succeeded: string[]
  skipped: string[]
  succeeded_count: number
  skipped_count: number
}

export interface BoardItem {
  id: string
  wp_code: string
  wp_name: string
  audit_cycle: string
  status: string
  review_status: string
  bucket: 'not_started' | 'in_progress' | 'pending_review' | 'passed'
  assigned_to: string | null
  reviewer: string | null
}

export interface CycleStat {
  not_started: number
  in_progress: number
  pending_review: number
  passed: number
  total: number
}

export interface ProgressBoardResult {
  cycles: Record<string, CycleStat>
  total: CycleStat
  board_items: BoardItem[]
}

export interface ProgressBrief {
  project_name: string
  generated_at: string
  completion_rate: number
  total_workpapers: number
  passed_count: number
  in_progress_count: number
  pending_review_count: number
  rejected_count: number
  not_started_count: number
  cycles_summary: Record<string, { total: number; passed: number; rate: number }>
  text_summary: string
  raw_summary?: string
  llm_polished?: boolean
}

export interface CrossRefIssue {
  type: 'missing' | 'incomplete'
  severity: 'high' | 'medium'
  source_code: string
  source_name: string
  target_code: string
  target_name: string
  message: string
}

export interface CrossRefCheckResult {
  total_refs: number
  issues: CrossRefIssue[]
  issue_count: number
  high_count: number
  medium_count: number
}

export interface CommitmentEntry {
  id?: string
  content: string
  due_date: string | null
  status?: 'pending' | 'done' | 'overdue'
  related_pbc_id?: string | null
  issue_ticket_id?: string | null
  completed_at?: string | null
}

export interface CommunicationRecord {
  id: string
  created_at: string
  created_by: string
  date: string
  contact_person: string
  topic: string
  content: string
  commitments: CommitmentEntry[] | string
  related_wp_codes: string[]
  related_accounts: string[]
}

// ── API Functions ──

/** 全局待复核收件箱 */
export async function getGlobalReviewInbox(page = 1, pageSize = 50): Promise<ReviewInboxResult> {
  const { data } = await http.get(P_rev.inbox.global, { params: { page, page_size: pageSize } })
  return data
}

/** 项目级待复核收件箱 */
export async function getProjectReviewInbox(projectId: string, page = 1, pageSize = 50): Promise<ReviewInboxResult> {
  const { data } = await http.get(P_rev.inbox.project(projectId), { params: { page, page_size: pageSize } })
  return data
}

/** 批量复核 */
export async function batchReview(projectId: string, wpIds: string[], action: 'approve' | 'reject', comment = ''): Promise<BatchReviewResult> {
  const { data } = await http.post(P_rev.batchReview(projectId), { wp_ids: wpIds, action, comment })
  return data
}

/** 项目进度看板 */
export async function getProgressBoard(projectId: string): Promise<ProgressBoardResult> {
  const { data } = await http.get(P_rev.progressBoard(projectId))
  return data
}

/** 项目进度简报 */
export async function getProgressBrief(projectId: string, polish = false): Promise<ProgressBrief> {
  const { data } = await http.get(P_rev.progressBrief(projectId), { params: { polish } })
  return data
}

/** 交叉引用检查 */
export async function checkCrossRefs(projectId: string): Promise<CrossRefCheckResult> {
  const { data } = await http.get(P_rev.crossRefCheck(projectId))
  return data
}

/** 客户沟通记录列表 */
export async function listCommunications(projectId: string): Promise<CommunicationRecord[]> {
  const { data } = await http.get(P_proj.communications.list(projectId))
  return Array.isArray(data) ? data : []
}

/** 新增客户沟通记录 */
export async function addCommunication(projectId: string, body: Partial<CommunicationRecord>): Promise<CommunicationRecord> {
  const { data } = await http.post(P_proj.communications.list(projectId), body)
  return data
}

/** 删除客户沟通记录 */
export async function deleteCommunication(projectId: string, commId: string): Promise<void> {
  await http.delete(P_proj.communications.detail(projectId, commId))
}

/** 导出审计调整汇总 Excel */
export async function exportAdjustmentSummary(projectId: string, year: number): Promise<void> {
  const response = await http.get(P_adj.exportSummary(projectId), {
    params: { year, format: 'excel' },
    responseType: 'blob',
  })
  const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `审计调整汇总_${year}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}
