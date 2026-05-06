/**
 * 质控规则管理 API
 */
import http from '@/utils/http'
import { qcRules as P } from './apiPaths'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface StandardRef {
  code: string
  section?: string
  name?: string
}

export interface QcRuleDefinition {
  id: string
  rule_code: string
  severity: 'blocking' | 'warning' | 'info'
  scope: 'workpaper' | 'project' | 'consolidation' | 'audit_log'
  category: string | null
  title: string
  description: string
  standard_ref: StandardRef[] | null
  expression_type: 'python' | 'jsonpath' | 'sql' | 'regex'
  expression: string
  parameters_schema: Record<string, any> | null
  enabled: boolean
  version: number
  created_by: string
  created_at: string
  updated_at: string
}

export interface QcRuleListParams {
  severity?: string
  scope?: string
  enabled?: boolean | null
  page?: number
  page_size?: number
}

export interface QcRuleListResponse {
  items: QcRuleDefinition[]
  total: number
}

// ─── API Paths ──────────────────────────────────────────────────────────────

// ─── API Functions ──────────────────────────────────────────────────────────

export async function getQcRules(params?: QcRuleListParams): Promise<QcRuleListResponse> {
  const { data } = await http.get(P.list, { params })
  // 后端可能直接返回数组或 {items, total} 结构
  if (Array.isArray(data)) {
    return { items: data, total: data.length }
  }
  return data
}

export async function getQcRule(ruleId: string): Promise<QcRuleDefinition> {
  const { data } = await http.get(P.detail(ruleId))
  return data
}

export async function createQcRule(payload: Partial<QcRuleDefinition>): Promise<QcRuleDefinition> {
  const { data } = await http.post(P.list, payload)
  return data
}

export async function updateQcRule(ruleId: string, payload: Partial<QcRuleDefinition>): Promise<QcRuleDefinition> {
  const { data } = await http.patch(P.detail(ruleId), payload)
  return data
}

export async function deleteQcRule(ruleId: string): Promise<void> {
  await http.delete(P.detail(ruleId))
}

export async function toggleQcRule(ruleId: string, enabled: boolean): Promise<QcRuleDefinition> {
  const { data } = await http.patch(P.detail(ruleId), { enabled })
  return data
}

// ─── Dry-Run ────────────────────────────────────────────────────────────────

export interface DryRunRequest {
  scope: 'project' | 'all'
  project_ids?: string[]
  sample_size?: number
}

export interface DryRunFinding {
  wp_id: string
  wp_code: string
  message: string
  severity: string
}

export interface DryRunResult {
  total_checked: number
  hits: number
  hit_rate: number
  sample_findings: DryRunFinding[]
}

export async function dryRunQcRule(ruleId: string, payload: DryRunRequest): Promise<DryRunResult> {
  const { data } = await http.post(P.dryRun(ruleId), payload)
  return data
}

// ─── Version History ────────────────────────────────────────────────────────

export interface QcRuleVersion {
  version: number
  rule_code: string
  title: string
  expression: string
  enabled: boolean
  updated_at: string
  updated_by: string
}

export async function getQcRuleVersions(ruleId: string): Promise<QcRuleVersion[]> {
  const { data } = await http.get(P.versions(ruleId))
  // 后端可能返回数组或 {items} 结构
  if (Array.isArray(data)) return data
  return data.items ?? []
}
