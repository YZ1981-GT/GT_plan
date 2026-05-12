/**
 * QC 审计日志合规抽查 API — Round 3 需求 12
 */
import http from '@/utils/http'
import { qcAuditLogCompliance as P } from './apiPaths'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface AuditLogFinding {
  id: string
  entry_id: string
  ts: string | null
  action_type: string
  user_id: string | null
  user_name: string | null
  ip: string | null
  rule_code: string
  rule_title: string | null
  severity: 'blocking' | 'warning' | 'info'
  message: string
  review_status: 'pending' | 'reviewed' | 'escalated'
  reviewed_by: string | null
  reviewed_at: string | null
}

export interface AuditLogComplianceResponse {
  items: AuditLogFinding[]
  total: number
}

export interface RunComplianceParams {
  project_id?: string
  time_window_hours?: number
}

export interface RunComplianceResult {
  message: string
  findings_count: number
  total_findings: number
}

export interface ComplianceSummary {
  total: number
  pending: number
  reviewed: number
  escalated: number
  by_rule: Record<string, number>
  by_severity: Record<string, number>
  findings: AuditLogFinding[]
}

// ─── API Paths ──────────────────────────────────────────────────────────────

// ─── API Functions ──────────────────────────────────────────────────────────

/** 获取日志合规命中条目列表 */
export async function getAuditLogFindings(params?: {
  project_id?: string
  status?: string
  page?: number
  page_size?: number
}): Promise<AuditLogComplianceResponse> {
  const { data } = await http.get(P.findings, { params })
  return data
}

/** 手动触发日志合规规则执行 */
export async function runAuditLogCompliance(
  payload: RunComplianceParams,
): Promise<RunComplianceResult> {
  const { data } = await http.post(P.run, payload)
  return data
}

/** 标记命中条目审查状态 */
export async function updateFindingStatus(
  findingId: string,
  status: 'reviewed' | 'escalated',
): Promise<AuditLogFinding> {
  const { data } = await http.patch(P.findingStatus(findingId), { status })
  return data
}

/** 获取日志合规抽查摘要（用于报告） */
export async function getComplianceSummary(params?: {
  project_id?: string
}): Promise<ComplianceSummary> {
  const { data } = await http.get(P.summary, { params })
  return data
}
