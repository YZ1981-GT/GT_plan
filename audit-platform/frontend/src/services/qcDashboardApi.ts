/**
 * 质控复核人员视角 API
 */
import http from '@/utils/http'
import { qcDashboard as P } from '@/services/apiPaths'

export interface QCOverview {
  total: number
  qc_passed: number
  qc_blocking: number
  qc_not_checked: number
  qc_checked: number
  qc_pass_rate: number
  review_distribution: Record<string, number>
  cycle_matrix: Record<string, Record<string, number>>
  recent_failures: Array<{
    wp_id: string
    blocking_count: number
    warning_count: number
    check_time: string | null
    findings: any[]
  }>
}

export interface StaffProgressItem {
  user_id: string
  user_name: string
  total: number
  passed: number
  pending_review: number
  rejected: number
  in_progress: number
  not_started: number
  completion_rate: number
}

export interface OpenIssue {
  wp_id: string | null
  content: string
  status: string
  created_by: string | null
  created_at: string | null
  cell_ref: string | null
}

export interface ArchiveCheck {
  id: string
  label: string
  passed: boolean
  detail: string
}

export interface ArchiveReadiness {
  ready: boolean
  checks: ArchiveCheck[]
  passed_count: number
  total_checks: number
  checked_at?: string
}

export async function getQCOverview(projectId: string): Promise<QCOverview> {
  const { data } = await http.get(P.overview(projectId))
  return data
}

export async function getStaffProgress(projectId: string): Promise<{ staff_progress: StaffProgressItem[]; staff_count: number }> {
  const { data } = await http.get(P.staffProgress(projectId))
  return data
}

export async function getOpenIssues(projectId: string): Promise<{ total_open: number; issues: OpenIssue[]; by_workpaper: Record<string, number> }> {
  const { data } = await http.get(P.openIssues(projectId))
  return data
}

export async function getArchiveReadiness(projectId: string): Promise<ArchiveReadiness> {
  const { data } = await http.get(P.archiveReadiness(projectId))
  return data
}

export async function runArchiveReadinessCheck(projectId: string): Promise<ArchiveReadiness> {
  const { data } = await http.post(P.archiveReadiness(projectId))
  return data
}
