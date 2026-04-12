/**
 * 底稿模块 API 服务层
 * 封装模板管理、取数公式、WOPI、底稿管理、质量自检、复核批注全部 API
 */
import http from '@/utils/http'

// ─── Types ───

export interface TemplateItem {
  id: string
  template_code: string
  template_name: string
  audit_cycle: string | null
  applicable_standard: string | null
  version_major: number
  version_minor: number
  status: string
  description: string | null
  created_at: string | null
}

export interface TemplateSetItem {
  id: string
  set_name: string
  template_codes: string[]
  applicable_audit_type: string | null
  applicable_standard: string | null
  description: string | null
}

export interface FormulaRequest {
  project_id: string
  year: number
  formula_type: string
  params: Record<string, any>
}

export interface FormulaResult {
  value: any
  error: string | null
  cached: boolean
}

export interface WpIndexItem {
  id: string
  wp_code: string
  wp_name: string
  audit_cycle: string | null
  status: string | null
  assigned_to: string | null
  reviewer: string | null
}

export interface WorkpaperDetail {
  id: string
  project_id: string
  wp_index_id: string
  file_path: string | null
  source_type: string
  status: string
  assigned_to: string | null
  reviewer: string | null
  file_version: number
  last_parsed_at: string | null
  created_at: string | null
  updated_at: string | null
  wp_code?: string
  wp_name?: string
  audit_cycle?: string
  qc_passed?: boolean | null
}

export interface QCFinding {
  rule_id: string
  severity: 'blocking' | 'warning' | 'info'
  message: string
  cell_reference: string | null
  expected_value: string | null
  actual_value: string | null
}

export interface QCResult {
  id: string
  working_paper_id: string
  check_timestamp: string | null
  findings: QCFinding[]
  passed: boolean | null
  blocking_count: number
  warning_count: number
  info_count: number
}

export interface QCSummary {
  total_workpapers: number
  passed_qc: number
  has_blocking: number
  not_started: number
  pass_rate: number
}

export interface ReviewComment {
  id: string
  working_paper_id: string
  cell_reference: string | null
  comment_text: string
  commenter_id: string
  status: string
  reply_text: string | null
  replier_id: string | null
  replied_at: string | null
  resolved_by: string | null
  resolved_at: string | null
  created_at: string | null
}

export interface CrossRefItem {
  id: string
  source_wp_id: string
  target_wp_code: string
  cell_reference: string | null
}

// ─── Template Management ───

export async function listTemplates(auditCycle?: string, standard?: string): Promise<TemplateItem[]> {
  const params: Record<string, string> = {}
  if (auditCycle) params.audit_cycle = auditCycle
  if (standard) params.applicable_standard = standard
  const { data } = await http.get('/api/templates', { params })
  return data.data ?? data
}

export async function uploadTemplate(body: {
  template_code: string; template_name: string;
  audit_cycle?: string; applicable_standard?: string;
  description?: string; named_ranges?: any[]
}): Promise<TemplateItem> {
  const { data } = await http.post('/api/templates', body)
  return data.data ?? data
}

export async function createTemplateVersion(code: string, changeType: string = 'minor'): Promise<TemplateItem> {
  const { data } = await http.post(`/api/templates/${code}/versions`, { change_type: changeType })
  return data.data ?? data
}

export async function deleteTemplate(templateId: string) {
  const { data } = await http.delete(`/api/templates/${templateId}`)
  return data.data ?? data
}

export async function listTemplateSets(): Promise<TemplateSetItem[]> {
  const { data } = await http.get('/api/template-sets')
  return data.data ?? data
}

export async function getTemplateSet(setId: string): Promise<TemplateSetItem> {
  const { data } = await http.get(`/api/template-sets/${setId}`)
  return data.data ?? data
}

export async function createTemplateSet(body: {
  set_name: string; template_codes?: string[];
  applicable_audit_type?: string; description?: string
}): Promise<TemplateSetItem> {
  const { data } = await http.post('/api/template-sets', body)
  return data.data ?? data
}

export async function updateTemplateSet(setId: string, body: Record<string, any>): Promise<TemplateSetItem> {
  const { data } = await http.put(`/api/template-sets/${setId}`, body)
  return data.data ?? data
}

// ─── Formula ───

export async function executeFormula(req: FormulaRequest): Promise<FormulaResult> {
  const { data } = await http.post('/api/formula/execute', req)
  return data.data ?? data
}

export async function batchExecuteFormulas(reqs: FormulaRequest[]): Promise<FormulaResult[]> {
  const { data } = await http.post('/api/formula/batch-execute', reqs)
  return data.data ?? data
}

// ─── Working Papers ───

export async function listWorkpapers(
  projectId: string,
  opts?: { audit_cycle?: string; status?: string; assigned_to?: string }
): Promise<WorkpaperDetail[]> {
  const { data } = await http.get(`/api/projects/${projectId}/working-papers`, { params: opts })
  return data.data ?? data
}

export async function getWorkpaper(projectId: string, wpId: string): Promise<WorkpaperDetail> {
  const { data } = await http.get(`/api/projects/${projectId}/working-papers/${wpId}`)
  return data.data ?? data
}

export async function downloadWorkpaper(projectId: string, wpId: string) {
  const { data } = await http.get(`/api/projects/${projectId}/working-papers/${wpId}/download`)
  return data.data ?? data
}

export async function uploadWorkpaper(projectId: string, wpId: string, recordedVersion: number) {
  const { data } = await http.post(`/api/projects/${projectId}/working-papers/${wpId}/upload`, {
    recorded_version: recordedVersion,
  })
  return data.data ?? data
}

export async function updateWorkpaperStatus(projectId: string, wpId: string, status: string) {
  const { data } = await http.put(`/api/projects/${projectId}/working-papers/${wpId}/status`, { status })
  return data.data ?? data
}

export async function assignWorkpaper(projectId: string, wpId: string, body: {
  assigned_to?: string | null; reviewer?: string | null
}) {
  const { data } = await http.put(`/api/projects/${projectId}/working-papers/${wpId}/assign`, body)
  return data.data ?? data
}

export async function prefillWorkpaper(projectId: string, wpId: string, year: number = 2025) {
  const { data } = await http.post(
    `/api/projects/${projectId}/working-papers/${wpId}/prefill`,
    null,
    { params: { year } },
  )
  return data.data ?? data
}

export async function parseWorkpaper(projectId: string, wpId: string) {
  const { data } = await http.post(`/api/projects/${projectId}/working-papers/${wpId}/parse`)
  return data.data ?? data
}

export async function getWpIndex(projectId: string): Promise<WpIndexItem[]> {
  const { data } = await http.get(`/api/projects/${projectId}/wp-index`)
  return data.data ?? data
}

export async function getWpCrossRefs(projectId: string): Promise<CrossRefItem[]> {
  const { data } = await http.get(`/api/projects/${projectId}/wp-cross-refs`)
  return data.data ?? data
}

// ─── QC ───

export async function runQCCheck(projectId: string, wpId: string): Promise<QCResult> {
  const { data } = await http.post(`/api/projects/${projectId}/working-papers/${wpId}/qc-check`)
  return data.data ?? data
}

export async function getQCResults(projectId: string, wpId: string): Promise<QCResult> {
  const { data } = await http.get(`/api/projects/${projectId}/working-papers/${wpId}/qc-results`)
  return data.data ?? data
}

export async function getQCSummary(projectId: string): Promise<QCSummary> {
  const { data } = await http.get(`/api/projects/${projectId}/qc-summary`)
  return data.data ?? data
}

// ─── Reviews ───

export async function listReviews(wpId: string, status?: string): Promise<ReviewComment[]> {
  const params: Record<string, string> = {}
  if (status) params.status = status
  const { data } = await http.get(`/api/working-papers/${wpId}/reviews`, { params })
  return data.data ?? data
}

export async function addReview(wpId: string, body: {
  commenter_id: string; comment_text: string; cell_reference?: string
}): Promise<ReviewComment> {
  const { data } = await http.post(`/api/working-papers/${wpId}/reviews`, body)
  return data.data ?? data
}

export async function replyReview(wpId: string, reviewId: string, body: {
  replier_id: string; reply_text: string
}): Promise<ReviewComment> {
  const { data } = await http.put(`/api/working-papers/${wpId}/reviews/${reviewId}/reply`, body)
  return data.data ?? data
}

export async function resolveReview(wpId: string, reviewId: string, body: {
  resolved_by: string
}): Promise<ReviewComment> {
  const { data } = await http.put(`/api/working-papers/${wpId}/reviews/${reviewId}/resolve`, body)
  return data.data ?? data
}

// ─── WOPI ───

export function getWopiEditorUrl(wpId: string, accessToken: string): string {
  const baseUrl = window.location.origin
  return `${baseUrl}/wopi/files/${wpId}?access_token=${encodeURIComponent(accessToken)}`
}


// ─── Sampling ───

export interface SamplingConfigItem {
  id: string
  project_id: string
  config_name: string
  sampling_type: string
  sampling_method: string
  applicable_scenario: string
  confidence_level: number | null
  expected_deviation_rate: number | null
  tolerable_deviation_rate: number | null
  tolerable_misstatement: number | null
  population_amount: number | null
  population_count: number | null
  calculated_sample_size: number | null
  created_at: string | null
}

export interface SamplingRecordItem {
  id: string
  project_id: string
  working_paper_id: string | null
  sampling_config_id: string | null
  sampling_purpose: string
  population_description: string
  population_total_amount: number | null
  population_total_count: number | null
  sample_size: number
  sampling_method_description: string | null
  deviations_found: number | null
  misstatements_found: number | null
  projected_misstatement: number | null
  upper_misstatement_limit: number | null
  conclusion: string | null
  created_at: string | null
}

export interface MUSEvaluationResult {
  projected_misstatement: number
  upper_misstatement_limit: number
  details: Array<{
    book_value: number
    misstatement_amount: number
    tainting_factor: number
    projected_misstatement: number
  }>
}

export async function listSamplingConfigs(projectId: string): Promise<SamplingConfigItem[]> {
  const { data } = await http.get(`/api/projects/${projectId}/sampling-configs`)
  return data.data ?? data
}

export async function createSamplingConfig(projectId: string, body: Record<string, any>): Promise<SamplingConfigItem> {
  const { data } = await http.post(`/api/projects/${projectId}/sampling-configs`, body)
  return data.data ?? data
}

export async function updateSamplingConfig(projectId: string, configId: string, body: Record<string, any>): Promise<SamplingConfigItem> {
  const { data } = await http.put(`/api/projects/${projectId}/sampling-configs/${configId}`, body)
  return data.data ?? data
}

export async function calculateSampleSize(projectId: string, body: Record<string, any>): Promise<{ method: string; params: Record<string, any>; calculated_size: number }> {
  const { data } = await http.post(`/api/projects/${projectId}/sampling-configs/calculate`, body)
  return data.data ?? data
}

export async function listSamplingRecords(projectId: string, workingPaperId?: string): Promise<SamplingRecordItem[]> {
  const params: Record<string, string> = {}
  if (workingPaperId) params.working_paper_id = workingPaperId
  const { data } = await http.get(`/api/projects/${projectId}/sampling-records`, { params })
  return data.data ?? data
}

export async function createSamplingRecord(projectId: string, body: Record<string, any>): Promise<SamplingRecordItem> {
  const { data } = await http.post(`/api/projects/${projectId}/sampling-records`, body)
  return data.data ?? data
}

export async function updateSamplingRecord(projectId: string, recordId: string, body: Record<string, any>): Promise<SamplingRecordItem> {
  const { data } = await http.put(`/api/projects/${projectId}/sampling-records/${recordId}`, body)
  return data.data ?? data
}

export async function musSamplingEvaluate(projectId: string, recordId: string, misstatementDetails: Array<{ book_value: number; misstatement_amount: number }>): Promise<MUSEvaluationResult> {
  const { data } = await http.post(`/api/projects/${projectId}/sampling-records/${recordId}/mus-evaluate`, {
    misstatement_details: misstatementDetails,
  })
  return data.data ?? data
}
