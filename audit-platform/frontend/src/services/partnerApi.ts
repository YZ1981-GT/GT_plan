/**
 * 合伙人视角 API
 */
import http from '@/utils/http'
import { partner as P, projects as P_proj } from '@/services/apiPaths'

export interface PartnerProject {
  id: string
  name: string
  client_name: string
  status: string
  wp_total: number
  wp_passed: number
  wp_pending: number
  wp_rejected: number
  completion_rate: number
  risk_level: 'high' | 'medium' | 'low'
  risk_reasons: string[]
}

export interface PartnerOverview {
  projects: PartnerProject[]
  total_projects: number
  risk_alerts: PartnerProject[]
  risk_alert_count: number
  pending_sign: PartnerProject[]
  pending_sign_count: number
}

export interface SignCheck {
  id: string
  label: string
  passed: boolean
  detail: string
}

export interface SignReadiness {
  ready_to_sign: boolean
  checks: SignCheck[]
  passed_count: number
  total_checks: number
}

export interface StaffMetric {
  user_id: string
  user_name: string
  total: number
  passed: number
  rejected: number
  pass_rate: number
  reject_rate: number
}

export interface TeamEfficiency {
  staff_metrics: StaffMetric[]
  summary: {
    total_staff: number
    total_workpapers: number
    avg_pass_rate: number
    avg_reject_rate: number
    avg_per_person: number
  }
}

export async function getPartnerOverview(): Promise<PartnerOverview> {
  const { data } = await http.get(P.overview)
  return data
}

export async function getSignReadiness(projectId: string): Promise<SignReadiness> {
  const { data } = await http.get(P_proj.signReadiness(projectId))
  return data
}

export async function getTeamEfficiency(days = 30): Promise<TeamEfficiency> {
  const { data } = await http.get(P.teamEfficiency, { params: { days } })
  return data
}
