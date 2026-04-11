/**
 * 审计作业平台 API 服务层
 * 封装所有后端 API 调用
 */
import http from '@/utils/http'

// ─── Trial Balance ───

export interface TrialBalanceRow {
  standard_account_code: string
  account_name: string | null
  account_category: string | null
  unadjusted_amount: string | null
  rje_adjustment: string
  aje_adjustment: string
  audited_amount: string | null
  opening_balance: string | null
  exceeds_materiality: boolean
  below_trivial: boolean
}

export async function getTrialBalance(projectId: string, year: number): Promise<TrialBalanceRow[]> {
  const { data } = await http.get(`/api/projects/${projectId}/trial-balance`, { params: { year } })
  return data.data ?? data
}

export async function recalcTrialBalance(projectId: string, year: number) {
  const { data } = await http.post(`/api/projects/${projectId}/trial-balance/recalc`, null, { params: { year } })
  return data.data ?? data
}

export interface ConsistencyResult {
  consistent: boolean
  issues: Array<{ account_code: string; field: string; expected: string; actual: string }>
}

export async function checkConsistency(projectId: string, year: number): Promise<ConsistencyResult> {
  const { data } = await http.get(`/api/projects/${projectId}/trial-balance/consistency-check`, { params: { year } })
  return data.data ?? data
}

// ─── Adjustments ───

export interface AdjustmentEntry {
  id: string
  entry_group_id: string
  adjustment_no: string
  adjustment_type: 'AJE' | 'RJE'
  description: string | null
  review_status: string
  created_by: string | null
  created_at: string
  total_debit: string
  total_credit: string
  line_items: AdjustmentLineItem[]
}

export interface AdjustmentLineItem {
  standard_account_code: string
  account_name: string | null
  report_line_code: string | null
  debit_amount: string
  credit_amount: string
}

export interface AdjustmentSummary {
  aje_count: number
  rje_count: number
  aje_total_debit: string
  aje_total_credit: string
  rje_total_debit: string
  rje_total_credit: string
  status_counts: Record<string, number>
}

export interface AccountOption {
  code: string
  name: string
  level: number
}

export async function listAdjustments(
  projectId: string, year: number,
  opts?: { adjustment_type?: string; review_status?: string; page?: number; page_size?: number }
) {
  const { data } = await http.get(`/api/projects/${projectId}/adjustments`, {
    params: { year, ...opts },
  })
  return data.data ?? data
}

export async function createAdjustment(projectId: string, body: {
  adjustment_type: string; year: number; company_code?: string;
  description?: string; line_items: Array<{
    standard_account_code: string; account_name?: string;
    debit_amount: number; credit_amount: number
  }>
}) {
  const { data } = await http.post(`/api/projects/${projectId}/adjustments`, body)
  return data.data ?? data
}

export async function updateAdjustment(projectId: string, groupId: string, body: {
  description?: string; line_items: Array<{
    standard_account_code: string; account_name?: string;
    debit_amount: number; credit_amount: number
  }>
}) {
  const { data } = await http.put(`/api/projects/${projectId}/adjustments/${groupId}`, body)
  return data.data ?? data
}

export async function deleteAdjustment(projectId: string, groupId: string) {
  const { data } = await http.delete(`/api/projects/${projectId}/adjustments/${groupId}`)
  return data.data ?? data
}

export async function reviewAdjustment(projectId: string, groupId: string, body: {
  status: string; reason?: string
}) {
  const { data } = await http.post(`/api/projects/${projectId}/adjustments/${groupId}/review`, body)
  return data.data ?? data
}

export async function getAdjustmentSummary(projectId: string, year: number): Promise<AdjustmentSummary> {
  const { data } = await http.get(`/api/projects/${projectId}/adjustments/summary`, { params: { year } })
  return data.data ?? data
}

export async function getAccountDropdown(projectId: string, reportLineCode?: string): Promise<AccountOption[]> {
  const params: Record<string, string> = {}
  if (reportLineCode) params.report_line_code = reportLineCode
  const { data } = await http.get(`/api/projects/${projectId}/adjustments/account-dropdown`, { params })
  return data.data ?? data
}

// ─── Materiality ───

export interface MaterialityData {
  benchmark_type: string
  benchmark_amount: string
  overall_percentage: string
  overall_materiality: string
  performance_ratio: string
  performance_materiality: string
  trivial_ratio: string
  trivial_threshold: string
  is_override: boolean
  override_reason: string | null
}

export async function getMateriality(projectId: string, year: number): Promise<MaterialityData | null> {
  const { data } = await http.get(`/api/projects/${projectId}/materiality`, { params: { year } })
  return data.data ?? data
}

export async function calculateMateriality(projectId: string, year: number, body: {
  benchmark_type: string; benchmark_amount: string;
  overall_percentage: string; performance_ratio: string; trivial_ratio: string
}): Promise<MaterialityData> {
  const { data } = await http.post(`/api/projects/${projectId}/materiality/calculate`, body, { params: { year } })
  return data.data ?? data
}

export async function overrideMateriality(projectId: string, year: number, body: {
  overall_materiality?: string; performance_materiality?: string;
  trivial_threshold?: string; override_reason: string
}): Promise<MaterialityData> {
  const { data } = await http.put(`/api/projects/${projectId}/materiality/override`, body, { params: { year } })
  return data.data ?? data
}

export async function getMaterialityHistory(projectId: string, year: number) {
  const { data } = await http.get(`/api/projects/${projectId}/materiality/history`, { params: { year } })
  return data.data ?? data
}

export async function getMaterialityBenchmark(projectId: string, year: number, benchmarkType: string) {
  const { data } = await http.get(`/api/projects/${projectId}/materiality/benchmark`, {
    params: { year, benchmark_type: benchmarkType },
  })
  return data.data ?? data
}

// ─── Events SSE ───

export function createEventSource(projectId: string): EventSource {
  return new EventSource(`/api/projects/${projectId}/events/stream`)
}


// ─── Misstatements (未更正错报) ───

export interface MisstatementItem {
  id: string
  project_id: string
  year: number
  source_adjustment_id: string | null
  misstatement_description: string
  affected_account_code: string | null
  affected_account_name: string | null
  misstatement_amount: string
  misstatement_type: string
  management_reason: string | null
  auditor_evaluation: string | null
  is_carried_forward: boolean
  prior_year_id: string | null
  created_by: string | null
  created_at: string | null
}

export interface MisstatementSummaryData {
  by_type: Array<{ misstatement_type: string; count: number; total_amount: string }>
  cumulative_amount: string
  overall_materiality: string | null
  performance_materiality: string | null
  trivial_threshold: string | null
  exceeds_materiality: boolean
  evaluation_complete: boolean
}

export async function listMisstatements(projectId: string, year: number): Promise<MisstatementItem[]> {
  const { data } = await http.get(`/api/projects/${projectId}/misstatements`, { params: { year } })
  return data.data ?? data
}

export async function createMisstatement(projectId: string, body: Record<string, any>) {
  const { data } = await http.post(`/api/projects/${projectId}/misstatements`, body)
  return data.data ?? data
}

export async function createMisstatementFromAje(projectId: string, groupId: string, year: number) {
  const { data } = await http.post(`/api/projects/${projectId}/misstatements/from-aje/${groupId}`, null, { params: { year } })
  return data.data ?? data
}

export async function updateMisstatement(projectId: string, misstatementId: string, body: Record<string, any>) {
  const { data } = await http.put(`/api/projects/${projectId}/misstatements/${misstatementId}`, body)
  return data.data ?? data
}

export async function deleteMisstatement(projectId: string, misstatementId: string) {
  const { data } = await http.delete(`/api/projects/${projectId}/misstatements/${misstatementId}`)
  return data.data ?? data
}

export async function getMisstatementSummary(projectId: string, year: number): Promise<MisstatementSummaryData> {
  const { data } = await http.get(`/api/projects/${projectId}/misstatements/summary`, { params: { year } })
  return data.data ?? data
}


// ─── Reports (财务报表) ───

export interface ReportRow {
  row_code: string
  row_name: string
  current_period_amount: string | null
  prior_period_amount: string | null
  formula_used: string | null
  source_accounts: string[] | null
  indent_level: number
  is_total_row: boolean
}

export interface ReportDrilldownData {
  row_code: string
  row_name: string
  formula: string
  accounts: Array<{ code: string; name: string; amount: string }>
}

export interface ReportConsistencyCheck {
  consistent: boolean
  checks: Array<{ name: string; passed: boolean; expected: string; actual: string; diff: string }>
}

export async function generateReports(projectId: string, year: number) {
  const { data } = await http.post('/api/reports/generate', { project_id: projectId, year })
  return data.data ?? data
}

export async function getReport(projectId: string, year: number, reportType: string): Promise<ReportRow[]> {
  const { data } = await http.get(`/api/reports/${projectId}/${year}/${reportType}`)
  return data.data ?? data
}

export async function getReportDrilldown(projectId: string, year: number, reportType: string, rowCode: string): Promise<ReportDrilldownData> {
  const { data } = await http.get(`/api/reports/${projectId}/${year}/${reportType}/drilldown/${rowCode}`)
  return data.data ?? data
}

export async function getReportConsistencyCheck(projectId: string, year: number): Promise<ReportConsistencyCheck> {
  const { data } = await http.get(`/api/reports/${projectId}/${year}/consistency-check`)
  return data.data ?? data
}

export function getReportExcelUrl(projectId: string, year: number, reportType: string): string {
  return `/api/reports/${projectId}/${year}/${reportType}/export-excel`
}

// ─── CFS Worksheet (现金流量表工作底稿) ───

export interface CFSWorksheetRow {
  account_code: string
  account_name: string
  opening_balance: string
  closing_balance: string
  period_change: string
  allocated_amount: string
  unallocated_amount: string
}

export interface CFSAdjustmentItem {
  id: string
  adjustment_no: string
  description: string
  debit_account: string
  credit_account: string
  amount: string
  cash_flow_category: string
  cash_flow_line_item: string
  is_auto_generated: boolean
}

export interface CFSReconciliation {
  balanced: boolean
  items: Array<{ account_code: string; account_name: string; change: string; allocated: string; unallocated: string }>
}

export interface CFSIndirectMethod {
  items: Array<{ label: string; amount: string; is_total: boolean }>
  operating_cash_flow: string
  reconciliation_passed: boolean
}

export async function generateCFSWorksheet(projectId: string, year: number) {
  const { data } = await http.post('/api/cfs-worksheet/generate', { project_id: projectId, year })
  return data.data ?? data
}

export async function getCFSWorksheet(projectId: string, year: number): Promise<CFSWorksheetRow[]> {
  const { data } = await http.get(`/api/cfs-worksheet/${projectId}/${year}`)
  return data.data ?? data
}

export async function createCFSAdjustment(body: Record<string, any>) {
  const { data } = await http.post('/api/cfs-worksheet/adjustments', body)
  return data.data ?? data
}

export async function updateCFSAdjustment(id: string, body: Record<string, any>) {
  const { data } = await http.put(`/api/cfs-worksheet/adjustments/${id}`, body)
  return data.data ?? data
}

export async function deleteCFSAdjustment(id: string) {
  const { data } = await http.delete(`/api/cfs-worksheet/adjustments/${id}`)
  return data.data ?? data
}

export async function getCFSReconciliation(projectId: string, year: number): Promise<CFSReconciliation> {
  const { data } = await http.get(`/api/cfs-worksheet/${projectId}/${year}/reconciliation`)
  return data.data ?? data
}

export async function autoGenerateCFSAdjustments(projectId: string, year: number) {
  const { data } = await http.post('/api/cfs-worksheet/auto-generate', { project_id: projectId, year })
  return data.data ?? data
}

export async function getCFSIndirectMethod(projectId: string, year: number): Promise<CFSIndirectMethod> {
  const { data } = await http.get(`/api/cfs-worksheet/${projectId}/${year}/indirect-method`)
  return data.data ?? data
}

export async function getCFSVerify(projectId: string, year: number) {
  const { data } = await http.get(`/api/cfs-worksheet/${projectId}/${year}/verify`)
  return data.data ?? data
}

// ─── Disclosure Notes (附注) ───

export interface DisclosureNoteTreeItem {
  id: string
  note_section: string
  section_title: string
  account_name: string | null
  content_type: string
  status: string
  sort_order: number
}

export interface DisclosureNoteDetail {
  id: string
  note_section: string
  section_title: string
  account_name: string | null
  content_type: string
  table_data: any
  text_content: string | null
  status: string
}

export interface NoteValidationFinding {
  note_section: string
  table_name: string
  check_type: string
  severity: string
  message: string
  expected_value: string | null
  actual_value: string | null
}

export async function generateDisclosureNotes(projectId: string, year: number, templateType: string = 'soe') {
  const { data } = await http.post('/api/disclosure-notes/generate', { project_id: projectId, year, template_type: templateType })
  return data.data ?? data
}

export async function getDisclosureNoteTree(projectId: string, year: number): Promise<DisclosureNoteTreeItem[]> {
  const { data } = await http.get(`/api/disclosure-notes/${projectId}/${year}`)
  return data.data ?? data
}

export async function getDisclosureNoteDetail(projectId: string, year: number, noteSection: string): Promise<DisclosureNoteDetail> {
  const { data } = await http.get(`/api/disclosure-notes/${projectId}/${year}/${noteSection}`)
  return data.data ?? data
}

export async function updateDisclosureNote(noteId: string, body: Record<string, any>) {
  const { data } = await http.put(`/api/disclosure-notes/${noteId}`, body)
  return data.data ?? data
}

export async function validateDisclosureNotes(projectId: string, year: number) {
  const { data } = await http.post(`/api/disclosure-notes/${projectId}/${year}/validate`)
  return data.data ?? data
}

export async function getValidationResults(projectId: string, year: number): Promise<NoteValidationFinding[]> {
  const { data } = await http.get(`/api/disclosure-notes/${projectId}/${year}/validation-results`)
  return data.data ?? data
}

// ─── Audit Report (审计报告) ───

export interface AuditReportData {
  id: string
  project_id: string
  year: number
  opinion_type: string
  company_type: string
  report_date: string | null
  signing_partner: string | null
  paragraphs: Record<string, string>
  financial_data: Record<string, any>
  status: string
}

export interface AuditReportTemplate {
  opinion_type: string
  company_type: string
  section_name: string
  section_order: number
  template_text: string
}

export async function generateAuditReport(projectId: string, year: number, opinionType: string, companyType: string = 'non_listed') {
  const { data } = await http.post('/api/audit-report/generate', { project_id: projectId, year, opinion_type: opinionType, company_type: companyType })
  return data.data ?? data
}

export async function getAuditReport(projectId: string, year: number): Promise<AuditReportData> {
  const { data } = await http.get(`/api/audit-report/${projectId}/${year}`)
  return data.data ?? data
}

export async function updateAuditReportParagraph(reportId: string, section: string, body: { content: string }) {
  const { data } = await http.put(`/api/audit-report/${reportId}/paragraphs/${section}`, body)
  return data.data ?? data
}

export async function getAuditReportTemplates(): Promise<AuditReportTemplate[]> {
  const { data } = await http.get('/api/audit-report/templates')
  return data.data ?? data
}

export async function updateAuditReportStatus(reportId: string, status: string) {
  const { data } = await http.put(`/api/audit-report/${reportId}/status`, { status })
  return data.data ?? data
}

// ─── PDF Export (PDF导出) ───

export interface ExportTaskData {
  id: string
  project_id: string
  task_type: string
  status: string
  progress_percentage: number
  file_path: string | null
  file_size: number | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export async function createExportTask(projectId: string, taskType: string, documentTypes: string[], passwordProtected: boolean = false, password?: string) {
  const { data } = await http.post('/api/export/create', {
    project_id: projectId,
    task_type: taskType,
    document_types: documentTypes,
    password_protected: passwordProtected,
    password,
  })
  return data.data ?? data
}

export async function getExportTaskStatus(taskId: string): Promise<ExportTaskData> {
  const { data } = await http.get(`/api/export/${taskId}/status`)
  return data.data ?? data
}

export function getExportDownloadUrl(taskId: string): string {
  return `/api/export/${taskId}/download`
}

export async function getExportHistory(projectId: string): Promise<ExportTaskData[]> {
  const { data } = await http.get(`/api/export/${projectId}/history`)
  return data.data ?? data
}
