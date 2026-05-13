/**
  * 审计作业平台 API 服务层
  * 封装所有后端 API 调用
  */
 import http from '@/utils/http'
 import {
   projects as P_proj, trialBalance as P_tb, adjustments as P_adj,
   materiality as P_mat, misstatements as P_mis, reports as P_rpt,
   cfsWorksheet as P_cfs, disclosureNotes as P_dn, auditReport as P_ar,
   exportTask as P_exp, workpaperSummary as P_ws, events as P_evt,
 } from '@/services/apiPaths'

 export interface ProjectListItem {
   id: string
   name?: string | null
   client_name?: string | null
   audit_year?: number | string | null
 }

 export async function listProjects(): Promise<ProjectListItem[]> {
   const { data } = await http.get(P_proj.list)
   return Array.isArray(data) ? data : (data?.items ?? [])
 }

 export async function getProject(projectId: string): Promise<ProjectListItem> {
  const { data } = await http.get(P_proj.detail(projectId))
  return data
}

export async function getProjectAuditYear(projectId: string): Promise<number | null> {
  const project = await getProject(projectId)
  const auditYear = Number(project?.audit_year)
  return Number.isFinite(auditYear) && auditYear > 2000 ? auditYear : null
}

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
  updated_at?: string | null
}

export async function getTrialBalance(projectId: string, year: number, companyCode?: string): Promise<TrialBalanceRow[]> {
  const params: Record<string, any> = { year }
  if (companyCode) params.company_code = companyCode
  const { data } = await http.get(P_tb.get(projectId), { params })
  return data
}

export async function recalcTrialBalance(projectId: string, year: number) {
  const { data } = await http.post(P_tb.recalc(projectId), null, { params: { year } })
  return data
}

export interface ConsistencyResult {
  consistent: boolean
  issues: Array<{ account_code: string; field: string; expected: string; actual: string }>
}

export async function checkConsistency(projectId: string, year: number): Promise<ConsistencyResult> {
  const { data } = await http.get(P_tb.consistencyCheck(projectId), { params: { year } })
  return data
}

// ─── Adjustments ───

export interface AdjustmentEntry {
  id: string
  entry_group_id: string
  adjustment_no: string
  adjustment_type: 'aje' | 'rje' | 'AJE' | 'RJE'
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
  report_line?: string  // 对应报表行次名称
}

export async function listAdjustments(
  projectId: string, year: number,
  opts?: { adjustment_type?: string; review_status?: string; page?: number; page_size?: number }
) {
  const { data } = await http.get(P_adj.list(projectId), {
    params: { year, ...opts },
  })
  return data
}

export async function createAdjustment(projectId: string, body: {
  adjustment_type: string; year: number; company_code?: string;
  description?: string; line_items: Array<{
    standard_account_code: string; account_name?: string;
    debit_amount: number; credit_amount: number
  }>
}, opts?: { batch_mode?: boolean }) {
  const params: Record<string, any> = {}
  if (opts?.batch_mode) params.batch_mode = true
  const { data } = await http.post(P_adj.create(projectId), body, { params })
  return data
}

export async function batchCommitAdjustments(projectId: string, year: number) {
  const { data } = await http.post(P_adj.batchCommit(projectId), null, { params: { year } })
  return data
}

export async function updateAdjustment(projectId: string, groupId: string, body: {
  description?: string; line_items: Array<{
    standard_account_code: string; account_name?: string;
    debit_amount: number; credit_amount: number
  }>
}) {
  const { data } = await http.put(P_adj.detail(projectId, groupId), body)
  return data
}

export async function deleteAdjustment(projectId: string, groupId: string) {
  const { data } = await http.delete(P_adj.detail(projectId, groupId))
  return data
}

export async function reviewAdjustment(projectId: string, groupId: string, body: {
  status: string; reason?: string
}) {
  const { data } = await http.post(P_adj.review(projectId, groupId), body)
  return data
}

export async function getAdjustmentSummary(projectId: string, year: number): Promise<AdjustmentSummary> {
  const { data } = await http.get(P_adj.summary(projectId), { params: { year } })
  return data
}

export async function getAccountDropdown(projectId: string, reportLineCode?: string): Promise<AccountOption[]> {
  const params: Record<string, string> = {}
  if (reportLineCode) params.report_line_code = reportLineCode
  const { data } = await http.get(P_adj.accountDropdown(projectId), { params })
  return data
}

// ─── AJE → 错报 一键转换（R1 需求 3 / Task 9） ───

export interface ConvertAjeToMisstatementResult {
  misstatement_id: string
  source_entry_group_id: string
  source_adjustment_id: string | null
  net_amount: string
  misstatement_type: string
  year: number
  adjustment_count: number
  created_at: string | null
}

export interface ConvertAjeAlreadyConverted {
  error_code: 'ALREADY_CONVERTED'
  message: string
  existing_misstatement_id: string
}

/**
 * 把被驳回的 AJE 组一键转为未更正错报。
 *
 * 后端：`POST /api/projects/{project_id}/adjustments/{entry_group_id}/convert-to-misstatement`
 *
 * 返回值：
 *   - 成功：`ConvertAjeToMisstatementResult`
 *   - 409 `ALREADY_CONVERTED`：axios 会抛错；调用方需捕获 `err.response?.status === 409`
 *     并读取 `err.response?.data?.detail` 获取 `existing_misstatement_id`。
 */
export async function convertAjeToMisstatement(
  projectId: string,
  entryGroupId: string,
  opts?: { force?: boolean },
): Promise<ConvertAjeToMisstatementResult> {
  const { data } = await http.post(
    P_adj.convertToMisstatement(projectId, entryGroupId),
    { force: !!opts?.force },
  )
  return data
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
  const { data } = await http.get(P_mat.get(projectId), { params: { year } })
  return data
}

export async function calculateMateriality(projectId: string, year: number, body: {
  benchmark_type: string; benchmark_amount: string;
  overall_percentage: string; performance_ratio: string; trivial_ratio: string
}): Promise<MaterialityData> {
  const { data } = await http.post(P_mat.calculate(projectId), body, { params: { year } })
  return data
}

export async function overrideMateriality(projectId: string, year: number, body: {
  overall_materiality?: string; performance_materiality?: string;
  trivial_threshold?: string; override_reason: string
}): Promise<MaterialityData> {
  const { data } = await http.put(P_mat.override(projectId), body, { params: { year } })
  return data
}

export async function getMaterialityHistory(projectId: string, year: number) {
  const { data } = await http.get(P_mat.history(projectId), { params: { year } })
  return data
}

export async function getMaterialityBenchmark(projectId: string, year: number, benchmarkType: string) {
  const { data } = await http.get(P_mat.benchmark(projectId), {
    params: { year, benchmark_type: benchmarkType },
  })
  return data
}

// ─── Events SSE ───
// createSSE（fetch+ReadableStream）在 ThreeColumnLayout.vue 中直接使用，token 通过 Authorization header 传输
// createEventSource 保留为兼容接口（当前无调用方）

export function createEventSource(projectId: string) {
  return import('@/utils/sse').then(({ createSSE }) => createSSE(P_evt.stream(projectId)))
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
  const { data } = await http.get(P_mis.list(projectId), { params: { year } })
  return data
}

export async function createMisstatement(projectId: string, body: Record<string, any>) {
  const { data } = await http.post(P_mis.create(projectId), body)
  return data
}

export async function createMisstatementFromAje(projectId: string, groupId: string, year: number) {
  const { data } = await http.post(P_mis.fromAje(projectId, groupId), null, { params: { year } })
  return data
}

export async function updateMisstatement(projectId: string, misstatementId: string, body: Record<string, any>) {
  const { data } = await http.put(P_mis.detail(projectId, misstatementId), body)
  return data
}

export async function deleteMisstatement(projectId: string, misstatementId: string) {
  const { data } = await http.delete(P_mis.detail(projectId, misstatementId))
  return data
}

export async function getMisstatementSummary(projectId: string, year: number): Promise<MisstatementSummaryData> {
  const { data } = await http.get(P_mis.summary(projectId), { params: { year } })
  return data
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
  accounts: Array<{
    code: string
    name: string
    amount: string
    unadjusted_amount?: string
    audited_amount?: string
    wp_id?: string | null
  }>
}

export interface ReportConsistencyCheck {
  consistent: boolean
  checks: Array<{ name: string; passed: boolean; expected: string; actual: string; diff: string }>
  total?: number
  logic_check_passed?: number
  logic_check_count?: number
  reasonability_passed?: number
  reasonability_count?: number
}

export async function generateReports(projectId: string, year: number) {
  const { data } = await http.post(P_rpt.generate, { project_id: projectId, year })
  return data
}

export async function getReport(projectId: string, year: number, reportType: string, unadjusted: boolean = false, applicableStandard?: string): Promise<ReportRow[]> {
  const params: any = {}
  if (unadjusted) params.unadjusted = true
  if (applicableStandard) params.applicable_standard = applicableStandard
  const { data } = await http.get(P_rpt.get(projectId, year, reportType), { params })
  return data
}

export async function getReportDrilldown(projectId: string, year: number, reportType: string, rowCode: string): Promise<ReportDrilldownData> {
  const { data: raw } = await http.get(P_rpt.drilldown(projectId, year, reportType, rowCode))
  return {
    row_code: raw.row_code,
    row_name: raw.row_name,
    formula: raw.formula,
    accounts: (raw.contributing_accounts || []).map((item: any) => ({
      code: item.account_code,
      name: item.account_name,
      amount: item.audited_amount ?? item.amount ?? '0',
      unadjusted_amount: item.unadjusted_amount ?? item.amount ?? '0',
      audited_amount: item.audited_amount ?? item.amount ?? '0',
      wp_id: item.wp_id ?? null,
    })),
  }
}

export async function getReportConsistencyCheck(projectId: string, year: number): Promise<ReportConsistencyCheck> {
  const { data: raw } = await http.get(P_rpt.consistencyCheck(projectId, year))
  return {
    consistent: raw.consistent ?? raw.all_passed ?? false,
    checks: (raw.checks || []).map((item: any) => ({
      name: item.name ?? item.check_name ?? '',
      passed: !!item.passed,
      expected: item.expected ?? item.expected_value ?? '',
      actual: item.actual ?? item.actual_value ?? '',
      diff: item.diff ?? item.difference ?? '',
    })),
  }
}

export function getReportExcelUrl(projectId: string, year: number, reportType: string): string {
  return P_rpt.exportExcel(projectId, year, reportType)
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
  const { data } = await http.post(P_cfs.generate, { project_id: projectId, year })
  return data
}

export async function getCFSWorksheet(projectId: string, year: number): Promise<CFSWorksheetRow[]> {
  const { data } = await http.get(P_cfs.get(projectId, year))
  return data
}

export async function createCFSAdjustment(body: Record<string, any>) {
  const { data } = await http.post(P_cfs.adjustments.create, body)
  return data
}

export async function updateCFSAdjustment(id: string, body: Record<string, any>) {
  const { data } = await http.put(P_cfs.adjustments.detail(id), body)
  return data
}

export async function deleteCFSAdjustment(id: string) {
  const { data } = await http.delete(P_cfs.adjustments.detail(id))
  return data
}

export async function getCFSReconciliation(projectId: string, year: number): Promise<CFSReconciliation> {
  const { data } = await http.get(P_cfs.reconciliation(projectId, year))
  return data
}

export async function autoGenerateCFSAdjustments(projectId: string, year: number) {
  const { data } = await http.post(P_cfs.autoGenerate, { project_id: projectId, year })
  return data
}

export async function getCFSIndirectMethod(projectId: string, year: number): Promise<CFSIndirectMethod> {
  const { data } = await http.get(P_cfs.indirectMethod(projectId, year))
  return data
}

export async function getCFSVerify(projectId: string, year: number) {
  const { data } = await http.get(P_cfs.verify(projectId, year))
  return data
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
  const { data } = await http.post(P_dn.generate, { project_id: projectId, year, template_type: templateType })
  return data
}

export async function getDisclosureNoteTree(projectId: string, year: number): Promise<DisclosureNoteTreeItem[]> {
  const { data } = await http.get(P_dn.tree(projectId, year))
  return data
}

export async function getDisclosureNoteDetail(projectId: string, year: number, noteSection: string): Promise<DisclosureNoteDetail> {
  const { data } = await http.get(P_dn.detail(projectId, year, noteSection))
  return data
}

export async function updateDisclosureNote(noteId: string, body: Record<string, any>) {
  const { data } = await http.put(P_dn.update(noteId), body)
  return data
}

export async function validateDisclosureNotes(projectId: string, year: number) {
  const { data } = await http.post(P_dn.validate(projectId, year))
  return data
}

export async function getValidationResults(projectId: string, year: number): Promise<NoteValidationFinding[]> {
  const { data } = await http.get(P_dn.validationResults(projectId, year))
  return data
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
  const { data } = await http.post(P_ar.generate, { project_id: projectId, year, opinion_type: opinionType, company_type: companyType })
  return data
}

export async function getAuditReport(projectId: string, year: number): Promise<AuditReportData> {
  const { data } = await http.get(P_ar.get(projectId, year))
  return data
}

export async function updateAuditReportParagraph(reportId: string, section: string, body: { content: string }) {
  const { data } = await http.put(P_ar.paragraph(reportId, section), body)
  return data
}

export async function getAuditReportTemplates(): Promise<AuditReportTemplate[]> {
  const { data } = await http.get(P_ar.templates)
  return data
}

export async function updateAuditReportStatus(reportId: string, status: string) {
  const { data } = await http.put(P_ar.status(reportId), { status })
  return data
}

export async function refreshAuditReportFinancialData(projectId: string, year: number) {
  const { data } = await http.post(P_ar.refreshFinancialData(projectId, year))
  return data
}

export async function exportAuditReportWord(projectId: string, year: number): Promise<Blob> {
  const { data } = await http.get(P_ar.exportWord(projectId, year), { responseType: 'blob' })
  return data
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
  const { data } = await http.post(P_exp.create, {
    project_id: projectId,
    task_type: taskType,
    document_types: documentTypes,
    password_protected: passwordProtected,
    password,
  })
  return data
}

export async function getExportTaskStatus(taskId: string): Promise<ExportTaskData> {
  const { data } = await http.get(P_exp.status(taskId))
  return data
}

export function getExportDownloadUrl(taskId: string): string {
  return P_exp.download(taskId)
}

export async function getExportHistory(projectId: string): Promise<ExportTaskData[]> {
  const { data } = await http.get(P_exp.history(projectId))
  return data
}


// ─── Workpaper Summary (底稿跨企业汇总) ───

export async function getChildCompanies(projectId: string) {
  const { data } = await http.get(P_proj.childCompanies(projectId))
  return data
}

export async function generateWorkpaperSummary(projectId: string, params: {
  year: number; account_codes: string[]; company_codes: string[]
}) {
  const { data } = await http.post(P_ws.generate(projectId), params)
  return data
}

export async function exportWorkpaperSummary(projectId: string, params: {
  year: number; account_codes: string[]; company_codes: string[]
}): Promise<Blob> {
  const { data } = await http.post(P_ws.export(projectId), params, {
    responseType: 'blob',
  })
  return data
}
