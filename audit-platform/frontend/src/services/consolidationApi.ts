/**
 * 合并报表 API 服务层
 * Phase 11 Task 22.1 — 完整重建
 */
import { api } from '@/services/apiProxy'

// ─── TypeScript 类型定义 ──────────────────────────────────────────────────────

export interface ConsolScopeItem {
  id: string
  project_id: string
  year: number
  company_code: string
  company_name: string
  shareholding: number
  consol_method: string
  is_included: boolean
  scope_change_type?: string
  acquisition_date?: string
  parent_code?: string
  functional_currency?: string
}

export interface ConsolScopeSummary {
  total_companies: number
  included_companies: number
  excluded_companies: number
  scope_changes: number
}

export interface ConsolTrialRow {
  id: string
  project_id: string
  year: number
  standard_account_code: string
  account_name: string
  account_category: string
  individual_sum: number
  consol_adjustment: number
  consol_elimination: number
  consol_amount: number
}

export interface ConsistencyCheckResult {
  is_balanced: boolean
  total_debit: number
  total_credit: number
  difference: number
  row_count: number
}

export interface EliminationEntry {
  id: string
  project_id: string
  entry_no: string
  year: number
  entry_type: string
  description: string
  related_company_codes: string[]
  review_status: string
  debit_amount: number
  credit_amount: number
  lines?: any[]
}

export interface EliminationSummary {
  entry_type: string
  count: number
  total_debit: number
  total_credit: number
}

export interface InternalTrade {
  id: string
  seller_company_code: string
  buyer_company_code: string
  trade_type: string
  trade_amount: number
  cost_amount?: number
  unrealized_profit?: number
}

export interface InternalArAp {
  id: string
  debtor_company_code: string
  creditor_company_code: string
  debtor_amount: number
  creditor_amount: number
  difference_amount?: number
}

export interface TransactionMatrix {
  company_codes: string[]
  matrix: Record<string, Record<string, number>>
}

export interface ComponentAuditor {
  id: string
  project_id: string
  firm_name: string
  contact_person?: string
  auditor_name?: string
  auditor_email?: string
  component_name?: string
  scope?: string
  status?: string
}

export interface Instruction {
  id: string
  component_auditor_id: string
  instruction_no?: string
  status: string
  content?: string
}

export interface InstructionResult {
  id: string
  component_auditor_id: string
  instruction_id?: string
  result_no?: string
  evaluation_status: string
  opinion_type?: string
  status?: string
  content?: string
}

export interface ComponentDashboard {
  total_auditors: number
  pending_instructions: number
  pending_results: number
  received_results: number
  non_standard_opinions: number
}

export interface GoodwillRow {
  id: string
  year: number
  subsidiary_company_code: string
  acquisition_cost?: number
  goodwill_amount?: number
  accumulated_impairment?: number
  is_negative_goodwill: boolean
}

export interface ForexRow {
  id: string
  year: number
  company_code: string
  functional_currency: string
  reporting_currency: string
  bs_closing_rate?: number
  pl_average_rate?: number
}

export interface MinorityInterestRow {
  id: string
  year: number
  subsidiary_company_code: string
  minority_share_ratio?: number
  minority_equity?: number
  minority_profit?: number
}

export interface ConsolReportRow {
  row_code: string
  row_name: string
  current_period_amount: number
  prior_period_amount: number
  is_bold: boolean
  is_total: boolean
}

export interface ConsolReportData {
  rows: ConsolReportRow[]
  report_type: string
}

export interface YoYAnalysis {
  row_code: string
  row_name: string
  current: number
  prior: number
  change: number
  change_pct: number
}

export interface ConsolScopeNote { section_code: string; section_title: string; content_type: string }
export interface SubsidiaryNote { company_code: string; company_name: string }
export interface GoodwillNote { subsidiary_company_code: string; goodwill_amount: number }
export interface MinorityInterestNote { subsidiary_company_code: string; minority_equity: number }
export interface InternalTradeNote { seller: string; buyer: string; amount: number }
export interface InternalArApNote { debtor: string; creditor: string; amount: number }
export interface ForexTranslationNote { company_code: string; functional_currency: string }

export interface WorksheetNode {
  company_code: string
  company_name: string
  children?: WorksheetNode[]
  [key: string]: any
}

export interface PivotResult {
  headers: string[]
  rows: Record<string, any>[]
  totals?: Record<string, number>
}

export interface QueryTemplate {
  id: string
  name: string
  row_dimension: string
  col_dimension: string
  value_field: string
  filters?: Record<string, any>
  transpose: boolean
  aggregation_mode: string
}

// ─── 合并范围 API ─────────────────────────────────────────────────────────────

export async function getConsolScope(projectId: string, year?: number): Promise<ConsolScopeItem[]> {
  const y = year ?? new Date().getFullYear() - 1
  return api.get(`/api/consolidation/scope?project_id=${projectId}&year=${y}`)
}

export async function createConsolScope(projectId: string, data: Partial<ConsolScopeItem>): Promise<ConsolScopeItem> {
  return api.post(`/api/consolidation/scope?project_id=${projectId}`, data)
}

export async function updateConsolScope(scopeId: string, projectId: string, data: Partial<ConsolScopeItem>): Promise<ConsolScopeItem> {
  return api.put(`/api/consolidation/scope/${scopeId}?project_id=${projectId}`, data)
}

export async function deleteConsolScope(scopeId: string, projectId: string): Promise<void> {
  return api.delete(`/api/consolidation/scope/${scopeId}?project_id=${projectId}`)
}

export async function batchUpdateScope(projectId: string, items: Partial<ConsolScopeItem>[]): Promise<ConsolScopeItem[]> {
  return api.post(`/api/consolidation/scope/batch?project_id=${projectId}`, { scope_items: items })
}

export async function getConsolScopeSummary(projectId: string, year: number): Promise<ConsolScopeSummary> {
  return api.get(`/api/consolidation/scope/summary?project_id=${projectId}&year=${year}`)
}

// ─── 合并试算表 API ───────────────────────────────────────────────────────────

export async function getConsolTrial(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return api.get(`/api/consolidation/trial?project_id=${projectId}&year=${year}`)
}

export async function getConsolTrialBalance(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return getConsolTrial(projectId, year)
}

export async function recalculateConsolTrial(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return api.post(`/api/consolidation/trial/recalculate?project_id=${projectId}&year=${year}`)
}

export async function checkConsolTrialConsistency(projectId: string, year: number): Promise<ConsistencyCheckResult> {
  return api.get(`/api/consolidation/trial/consistency-check?project_id=${projectId}&year=${year}`)
}

// ─── 抵消分录 API ─────────────────────────────────────────────────────────────

export async function getEliminations(projectId: string, year?: number): Promise<EliminationEntry[]> {
  let url = `/api/consolidation/eliminations?project_id=${projectId}`
  if (year) url += `&year=${year}`
  return api.get(url)
}

export async function createElimination(projectId: string, data: any): Promise<EliminationEntry> {
  return api.post(`/api/consolidation/eliminations?project_id=${projectId}`, data)
}

export async function updateElimination(entryId: string, projectId: string, data: any): Promise<EliminationEntry> {
  return api.put(`/api/consolidation/eliminations/${entryId}?project_id=${projectId}`, data)
}

export async function deleteElimination(entryId: string, projectId: string): Promise<void> {
  return api.delete(`/api/consolidation/eliminations/${entryId}?project_id=${projectId}`)
}

export async function reviewElimination(entryId: string, projectId: string, action: any): Promise<EliminationEntry> {
  return api.post(`/api/consolidation/eliminations/${entryId}/review?project_id=${projectId}`, action)
}

export async function getEliminationSummary(projectId: string, year: number): Promise<EliminationSummary[]> {
  return api.get(`/api/consolidation/eliminations/summary/year?project_id=${projectId}&year=${year}`)
}

// ─── 内部交易 API ─────────────────────────────────────────────────────────────

export async function getInternalTrades(projectId: string, year: number): Promise<InternalTrade[]> {
  return api.get(`/api/consolidation/internal-trade/trades?project_id=${projectId}&year=${year}`)
}

export async function createInternalTrade(projectId: string, data: any): Promise<InternalTrade> {
  return api.post(`/api/consolidation/internal-trade/trades?project_id=${projectId}`, data)
}

export async function getInternalArAp(projectId: string, year: number): Promise<InternalArAp[]> {
  return api.get(`/api/consolidation/internal-trade/arap?project_id=${projectId}&year=${year}`)
}

export async function getTransactionMatrix(projectId: string, year: number): Promise<TransactionMatrix> {
  return api.get(`/api/consolidation/internal-trade/matrix?project_id=${projectId}&year=${year}`)
}

// ─── 组成部分审计师 API ───────────────────────────────────────────────────────

export async function getComponentAuditors(projectId: string): Promise<ComponentAuditor[]> {
  return api.get(`/api/consolidation/component-auditor/auditors?project_id=${projectId}`)
}

export async function createComponentAuditor(projectId: string, data: any): Promise<ComponentAuditor> {
  return api.post(`/api/consolidation/component-auditor/auditors?project_id=${projectId}`, data)
}

export async function getInstructions(projectId: string, auditorId?: string): Promise<Instruction[]> {
  let url = `/api/consolidation/component-auditor/instructions?project_id=${projectId}`
  if (auditorId) url += `&auditor_id=${auditorId}`
  return api.get(url)
}

export async function getResults(projectId: string, auditorId?: string): Promise<InstructionResult[]> {
  let url = `/api/consolidation/component-auditor/results?project_id=${projectId}`
  if (auditorId) url += `&auditor_id=${auditorId}`
  return api.get(url)
}

export async function createResult(projectId: string, data: any): Promise<InstructionResult> {
  return api.post(`/api/consolidation/component-auditor/results?project_id=${projectId}`, data)
}

export async function updateResult(resultId: string, projectId: string, data: any): Promise<InstructionResult> {
  return api.put(`/api/consolidation/component-auditor/results/${resultId}?project_id=${projectId}`, data)
}

export async function getComponentDashboard(projectId: string): Promise<ComponentDashboard> {
  return api.get(`/api/consolidation/component-auditor/dashboard?project_id=${projectId}`)
}

// ─── 商誉 API ─────────────────────────────────────────────────────────────────

export async function getGoodwillRows(projectId: string, year: number): Promise<GoodwillRow[]> {
  return api.get(`/api/consolidation/goodwill?project_id=${projectId}&year=${year}`)
}

export async function createGoodwill(projectId: string, data: any): Promise<GoodwillRow> {
  return api.post(`/api/consolidation/goodwill?project_id=${projectId}`, data)
}

// ─── 外币折算 API ─────────────────────────────────────────────────────────────

export async function getForexRows(projectId: string, year: number): Promise<ForexRow[]> {
  return api.get(`/api/consolidation/forex?project_id=${projectId}&year=${year}`)
}

// ─── 少数股东权益 API ─────────────────────────────────────────────────────────

export async function getMinorityInterestRows(projectId: string, year: number): Promise<MinorityInterestRow[]> {
  return api.get(`/api/consolidation/minority-interest?project_id=${projectId}&year=${year}`)
}

export async function getMinorityInterest(projectId: string, year: number): Promise<MinorityInterestRow[]> {
  return getMinorityInterestRows(projectId, year)
}

// ─── 合并附注 API ─────────────────────────────────────────────────────────────

export async function getConsolNotes(projectId: string, year: number): Promise<any[]> {
  return api.get(`/api/consolidation/notes/${projectId}/${year}`)
}

export async function createConsolNotes(projectId: string, year: number): Promise<any[]> {
  return api.post(`/api/consolidation/notes/${projectId}/${year}`)
}

export async function saveConsolNotes(projectId: string, period: string, data: any): Promise<any> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  return api.post(`/api/consolidation/notes/${projectId}/${year}/save`)
}

export async function getConsolScopeNotes(projectId: string, period: string): Promise<ConsolScopeNote[]> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  const notes = await getConsolNotes(projectId, year)
  return notes.filter((n: any) => n.section_code?.startsWith('scope'))
}

export async function getSubsidiaryNotes(projectId: string, period: string): Promise<SubsidiaryNote[]> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  const notes = await getConsolNotes(projectId, year)
  return notes.filter((n: any) => n.section_code?.startsWith('subsidiary'))
}

export async function getGoodwillNotes(projectId: string, period: string): Promise<GoodwillNote[]> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  const notes = await getConsolNotes(projectId, year)
  return notes.filter((n: any) => n.section_code?.startsWith('goodwill'))
}

export async function getMinorityInterestNotes(projectId: string, period: string): Promise<MinorityInterestNote[]> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  const notes = await getConsolNotes(projectId, year)
  return notes.filter((n: any) => n.section_code?.startsWith('minority'))
}

export async function getInternalTradeNotes(projectId: string, period: string): Promise<{ trades: InternalTradeNote[]; arap: InternalArApNote[] }> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  const notes = await getConsolNotes(projectId, year)
  return {
    trades: notes.filter((n: any) => n.section_code?.startsWith('internal_trade')),
    arap: notes.filter((n: any) => n.section_code?.startsWith('internal_arap')),
  }
}

export async function getForexTranslationNotes(projectId: string, period: string): Promise<ForexTranslationNote[]> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  const notes = await getConsolNotes(projectId, year)
  return notes.filter((n: any) => n.section_code?.startsWith('forex'))
}

// ─── 合并报表 API ─────────────────────────────────────────────────────────────

export async function getConsolReports(projectId: string, year: number): Promise<ConsolReportRow[]> {
  return api.get(`/api/consolidation/reports/${projectId}/${year}?report_type=balance_sheet`)
}

export async function getConsolReport(projectId: string, reportType: string, period: string): Promise<ConsolReportData> {
  const year = parseInt(period) || new Date().getFullYear() - 1
  const rows = await api.get(`/api/consolidation/reports/${projectId}/${year}?report_type=${reportType}`)
  return { rows: Array.isArray(rows) ? rows : [], report_type: reportType }
}

export async function saveConsolReport(projectId: string, reportType: string, period: string, data: ConsolReportData): Promise<ConsolReportData> {
  return data // 报表数据由后端生成，前端只读
}

export async function getYoYAnalysis(projectId: string, reportType: string, period: string): Promise<YoYAnalysis[]> {
  return [] // 同比分析待后端实现
}

export async function generateConsolReports(projectId: string, year: number, standard?: string): Promise<any> {
  return api.post('/api/consolidation/reports/generate', {
    project_id: projectId, year, applicable_standard: standard || 'CAS',
  })
}

export async function checkConsolBalance(projectId: string, year: number): Promise<any> {
  return api.get(`/api/consolidation/reports/${projectId}/${year}/balance-check`)
}

// ─── 差额表 / 工作底稿 API ───────────────────────────────────────────────────

export async function getWorksheetTree(projectId: string): Promise<any> {
  return api.get(`/api/consolidation/worksheet/tree?project_id=${projectId}`)
}

export async function recalcWorksheet(projectId: string, year: number): Promise<any> {
  return api.post('/api/consolidation/worksheet/recalc', { project_id: projectId, year })
}

export async function getWorksheetAggregate(projectId: string, year: number, nodeCode: string, mode: string = 'self'): Promise<any> {
  return api.get(`/api/consolidation/worksheet/aggregate?project_id=${projectId}&year=${year}&node_code=${nodeCode}&mode=${mode}`)
}

export async function drillToCompanies(projectId: string, year: number, nodeCode: string, accountCode?: string): Promise<any> {
  let url = `/api/consolidation/worksheet/drill/companies?project_id=${projectId}&year=${year}&node_code=${nodeCode}`
  if (accountCode) url += `&account_code=${accountCode}`
  return api.get(url)
}

export async function drillToEliminations(projectId: string, year: number, companyCode: string, accountCode?: string): Promise<any> {
  let url = `/api/consolidation/worksheet/drill/eliminations?project_id=${projectId}&year=${year}&company_code=${companyCode}`
  if (accountCode) url += `&account_code=${accountCode}`
  return api.get(url)
}

export async function drillToTrialBalance(projectId: string, companyCode: string): Promise<any> {
  return api.get(`/api/consolidation/worksheet/drill/trial-balance?project_id=${projectId}&company_code=${companyCode}`)
}

export async function executePivotQuery(projectId: string, year: number, params: any): Promise<PivotResult> {
  return api.post('/api/consolidation/worksheet/pivot', { project_id: projectId, year, ...params })
}

export async function exportPivotExcel(projectId: string, year: number, params: any): Promise<void> {
  const qs = new URLSearchParams({
    project_id: projectId, year: String(year),
    row_dimension: params.row_dimension || 'account',
    col_dimension: params.col_dimension || 'company',
    value_field: params.value_field || 'consolidated_amount',
    transpose: String(params.transpose || false),
    aggregation_mode: params.aggregation_mode || 'self',
  })
  window.open(`/api/consolidation/worksheet/pivot/export?${qs}`, '_blank')
}

export async function saveQueryTemplate(projectId: string, name: string, params: any): Promise<QueryTemplate> {
  return api.post('/api/consolidation/worksheet/pivot/templates', { project_id: projectId, name, ...params })
}

export async function listQueryTemplates(projectId: string): Promise<QueryTemplate[]> {
  const res = await api.get(`/api/consolidation/worksheet/pivot/templates?project_id=${projectId}`)
  return res?.templates || []
}
