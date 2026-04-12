/**
 * 合并报表 API 服务层
 */
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ComponentAuditor {
  id: string
  project_id: string
  component_name: string
  auditor_name: string
  auditor_email: string
  scope: string
  status: string
  created_at: string
}

export interface Instruction {
  id: string
  component_auditor_id: string
  instruction_no: string
  content: string
  issued_date: string
  due_date: string
  status: string
}

export interface InstructionResult {
  id: string
  instruction_id: string
  component_auditor_id: string
  result_no: string
  summary: string
  received_date: string
  status: string
  attachments: string[]
}

export interface ConsolTrialRow {
  id: string
  project_id: string
  account_code: string
  account_name: string
  entity_name: string
  local_amount: string
  consolidation_amount: string
  consolidation_adjustment: string
  final_amount: string
  currency: string
  exchange_rate: string
}

export interface ConsolTrialUpdate {
  consolidation_adjustment?: string
  exchange_rate?: string
}

export interface InternalTrade {
  id: string
  project_id: string
  year: number
  entity_name: string
  counterparty_name: string
  trade_type: string
  amount: string
  currency: string
  description: string
  status: string
}

export interface GoodwillRow {
  id: string
  project_id: string
  year: number
  cash_generating_unit: string
  acquisition_name: string
  initial_amount: string
  cumulative_impairment: string
  net_amount: string
  impairment_test_date: string
  recoverable_amount: string
  notes: string
}

export interface ForexRow {
  id: string
  project_id: string
  year: number
  entity_name: string
  currency: string
  functional_currency: string
  exchange_rate_used: string
  monetary_assets: string
  monetary_liabilities: string
  translation_differences: string
  notes: string
}

export interface MinorityInterestRow {
  id: string
  project_id: string
  year: number
  subsidiary_name: string
  ownership_percentage: string
  total_equity: string
  minority_percentage: string
  minority_interest_amount: string
  changes: string
  notes: string
}

export interface ConsistencyCheckResult {
  consistent: boolean
  checks: Array<{ name: string; passed: boolean; expected: string; actual: string; diff: string }>
}

// ─── Component Auditor ────────────────────────────────────────────────────────

export async function getComponentAuditors(projectId: string): Promise<ComponentAuditor[]> {
  const { data } = await http.get(`/api/consolidation/component-auditors`, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function createComponentAuditor(projectId: string, payload: Omit<ComponentAuditor, 'id' | 'created_at'>): Promise<ComponentAuditor> {
  const { data } = await http.post(`/api/consolidation/component-auditors`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function updateComponentAuditor(id: string, projectId: string, payload: Partial<ComponentAuditor>): Promise<ComponentAuditor> {
  const { data } = await http.put(`/api/consolidation/component-auditors/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteComponentAuditor(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/component-auditors/${id}`, { params: { project_id: projectId } })
}

// ─── Instructions ─────────────────────────────────────────────────────────────

export async function getInstructions(projectId: string): Promise<Instruction[]> {
  const { data } = await http.get(`/api/consolidation/instructions`, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function createInstruction(projectId: string, payload: Omit<Instruction, 'id'>): Promise<Instruction> {
  const { data } = await http.post(`/api/consolidation/instructions`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function updateInstruction(id: string, projectId: string, payload: Partial<Instruction>): Promise<Instruction> {
  const { data } = await http.put(`/api/consolidation/instructions/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteInstruction(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/instructions/${id}`, { params: { project_id: projectId } })
}

// ─── Results ─────────────────────────────────────────────────────────────────

export async function getResults(projectId: string): Promise<InstructionResult[]> {
  const { data } = await http.get(`/api/consolidation/results`, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function createResult(projectId: string, payload: Omit<InstructionResult, 'id'>): Promise<InstructionResult> {
  const { data } = await http.post(`/api/consolidation/results`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function updateResult(id: string, projectId: string, payload: Partial<InstructionResult>): Promise<InstructionResult> {
  const { data } = await http.put(`/api/consolidation/results/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteResult(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/results/${id}`, { params: { project_id: projectId } })
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export async function getComponentDashboard(projectId: string) {
  const { data } = await http.get(`/api/consolidation/component-auditors/dashboard`, { params: { project_id: projectId } })
  return data.data ?? data
}

// ─── Consol Trial Balance ────────────────────────────────────────────────────

export async function getConsolTrialBalance(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  const { data } = await http.get('/api/consolidation/trial', { params: { project_id: projectId, year } })
  return data.data ?? data
}

export async function updateConsolTrialRow(id: string, projectId: string, payload: Partial<ConsolTrialUpdate>): Promise<ConsolTrialRow> {
  const { data } = await http.put(`/api/consolidation/trial/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function recalcConsolTrial(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  const { data } = await http.post('/api/consolidation/trial/recalculate', {}, { params: { project_id: projectId, year } })
  return data.data ?? data
}

export async function checkConsolTrialConsistency(projectId: string, year: number): Promise<ConsistencyCheckResult> {
  const { data } = await http.get('/api/consolidation/trial/consistency-check', { params: { project_id: projectId, year } })
  return data.data ?? data
}

export async function deleteConsolTrialRow(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/trial/${id}`, { params: { project_id: projectId } })
}

// ─── Internal Trade ──────────────────────────────────────────────────────────

export async function getInternalTrades(projectId: string, year?: number): Promise<InternalTrade[]> {
  const { data } = await http.get('/api/consolidation/internal-trades', { params: { project_id: projectId, ...(year && { year }) } })
  return data.data ?? data
}

export async function createInternalTrade(projectId: string, payload: Omit<InternalTrade, 'id'>): Promise<InternalTrade> {
  const { data } = await http.post('/api/consolidation/internal-trades', payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function updateInternalTrade(id: string, projectId: string, payload: Partial<InternalTrade>): Promise<InternalTrade> {
  const { data } = await http.put(`/api/consolidation/internal-trades/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteInternalTrade(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/internal-trades/${id}`, { params: { project_id: projectId } })
}

// ─── Goodwill ─────────────────────────────────────────────────────────────────

export async function getGoodwillRows(projectId: string, year?: number): Promise<GoodwillRow[]> {
  const { data } = await http.get('/api/consolidation/goodwill', { params: { project_id: projectId, ...(year && { year }) } })
  return data.data ?? data
}

export async function createGoodwillRow(projectId: string, payload: Omit<GoodwillRow, 'id'>): Promise<GoodwillRow> {
  const { data } = await http.post('/api/consolidation/goodwill', payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function updateGoodwillRow(id: string, projectId: string, payload: Partial<GoodwillRow>): Promise<GoodwillRow> {
  const { data } = await http.put(`/api/consolidation/goodwill/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteGoodwillRow(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/goodwill/${id}`, { params: { project_id: projectId } })
}

// ─── Forex ───────────────────────────────────────────────────────────────────

export async function getForexRows(projectId: string, year?: number): Promise<ForexRow[]> {
  const { data } = await http.get('/api/consolidation/forex', { params: { project_id: projectId, ...(year && { year }) } })
  return data.data ?? data
}

export async function createForexRow(projectId: string, payload: Omit<ForexRow, 'id'>): Promise<ForexRow> {
  const { data } = await http.post('/api/consolidation/forex', payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function updateForexRow(id: string, projectId: string, payload: Partial<ForexRow>): Promise<ForexRow> {
  const { data } = await http.put(`/api/consolidation/forex/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteForexRow(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/forex/${id}`, { params: { project_id: projectId } })
}

// ─── Minority Interest ─────────────────────────────────────────────────────────

export async function getMinorityInterestRows(projectId: string, year?: number): Promise<MinorityInterestRow[]> {
  const { data } = await http.get('/api/consolidation/minority-interest', { params: { project_id: projectId, ...(year && { year }) } })
  return data.data ?? data
}

export async function createMinorityInterestRow(projectId: string, payload: Omit<MinorityInterestRow, 'id'>): Promise<MinorityInterestRow> {
  const { data } = await http.post('/api/consolidation/minority-interest', payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function updateMinorityInterestRow(id: string, projectId: string, payload: Partial<MinorityInterestRow>): Promise<MinorityInterestRow> {
  const { data } = await http.put(`/api/consolidation/minority-interest/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteMinorityInterestRow(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/minority-interest/${id}`, { params: { project_id: projectId } })
}

// ─── Company Structure ───────────────────────────────────────────────────────

export interface CompanyTreeNode {
  id: string
  projectId: string
  companyCode: string
  companyName: string
  parentCode: string | null
  ultimateCode: string
  consolLevel: number
  shareholding: number | null
  consolMethod: ConsolMethod | null
  acquisitionDate: string | null
  disposalDate: string | null
  functionalCurrency: string
  isActive: boolean
  isDeleted: boolean
  createdAt: string
  updatedAt: string
  children: CompanyTreeNode[]
}

export type ConsolMethod = 'full' | 'proportional' | 'equity'

export interface CompanyCreatePayload {
  project_id: string
  company_code: string
  company_name: string
  parent_code?: string | null
  ultimate_code: string
  consol_level?: number
  shareholding?: number | null
  consol_method?: ConsolMethod | null
  acquisition_date?: string | null
  disposal_date?: string | null
  functional_currency?: string
  is_active?: boolean
}

export interface CompanyUpdatePayload {
  company_name?: string | null
  parent_code?: string | null
  ultimate_code?: string | null
  consol_level?: number | null
  shareholding?: number | null
  consol_method?: ConsolMethod | null
  acquisition_date?: string | null
  disposal_date?: string | null
  functional_currency?: string | null
  is_active?: boolean | null
}

export async function getCompanyTree(projectId: string, year: number): Promise<CompanyTreeNode[]> {
  const { data } = await http.get('/api/consolidation/structure', { params: { project_id: projectId, year } })
  return data.data ?? data ?? []
}

export async function createCompany(payload: CompanyCreatePayload): Promise<CompanyTreeNode> {
  const { data } = await http.post('/api/consolidation/companies', payload)
  return data.data ?? data
}

export async function updateCompany(id: string, projectId: string, payload: CompanyUpdatePayload): Promise<CompanyTreeNode> {
  const { data } = await http.put(`/api/consolidation/companies/${id}`, payload, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function deleteCompany(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/companies/${id}`, { params: { project_id: projectId } })
}

// ─── Consol Scope ────────────────────────────────────────────────────────────

export interface ConsolScopeRow {
  id: string
  project_id: string
  year: number
  company_code: string
  company_name?: string
  is_included: boolean
  inclusion_reason: string | null
  exclusion_reason: string | null
  scope_change_type: string
  scope_change_description: string | null
  notes: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface ConsolScopeUpdatePayload {
  is_included?: boolean
  inclusion_reason?: string | null
  exclusion_reason?: string | null
  scope_change_type?: string
  scope_change_description?: string | null
  notes?: string | null
}

export async function getConsolScope(projectId: string, year: number): Promise<ConsolScopeRow[]> {
  const { data } = await http.get('/api/consolidation/scope', { params: { project_id: projectId, year } })
  return data.data ?? data ?? []
}

export async function batchUpdateConsolScope(projectId: string, year: number, items: ConsolScopeUpdatePayload[]): Promise<ConsolScopeRow[]> {
  const { data } = await http.post('/api/consolidation/scope', { scope_items: items, project_id: projectId, year }, { params: { project_id: projectId, year } })
  return data.data ?? data ?? []
}


// ─── Elimination Entry Types ─────────────────────────────────────────────────

export type EliminationEntryType = 
  | 'investment'    // 投资类
  | 'ar_ap'         // 往来类
  | 'transaction'   // 交易类
  | 'internal_income' // 内部收入类
  | 'other'         // 其他

export type ReviewStatus = 'draft' | 'pending_review' | 'approved' | 'rejected'

export interface EliminationLineItem {
  id?: string
  account_code: string
  account_name?: string
  debit_amount: number
  credit_amount: number
  currency?: string
  remark?: string
}

export interface EliminationEntry {
  id: string
  project_id: string
  year: number
  entry_no: string
  entry_type: EliminationEntryType
  description: string
  lines: EliminationLineItem[]
  related_company_codes: string[]
  related_company_names?: string[]
  is_continuous: boolean
  prior_year_entry_id?: string | null
  review_status: ReviewStatus
  reject_reason?: string | null
  created_by?: string
  created_at: string
  updated_at: string
}

export interface EliminationEntryCreatePayload {
  project_id: string
  year: number
  entry_type: EliminationEntryType
  description: string
  lines: Omit<EliminationLineItem, 'id'>[]
  related_company_codes: string[]
  currency?: string
}

export interface EliminationEntryUpdatePayload {
  entry_type?: EliminationEntryType
  description?: string
  lines?: Omit<EliminationLineItem, 'id'>[]
  related_company_codes?: string[]
  currency?: string
}

export interface EliminationListFilter {
  year?: number
  entry_type?: EliminationEntryType | ''
  review_status?: ReviewStatus | ''
}

export interface EliminationSummary {
  year: number
  by_type: Record<EliminationEntryType, { count: number; debit_sum: number; credit_sum: number }>
  total_count: number
  total_debit: number
  total_credit: number
}

export interface CarryForwardResult {
  carried_count: number
  adjusted_entries: string[]
  errors: string[]
}

// ─── Elimination Entry API ────────────────────────────────────────────────────

export async function getEliminationEntries(
  projectId: string,
  filters?: EliminationListFilter
): Promise<EliminationEntry[]> {
  const params: Record<string, unknown> = { project_id: projectId }
  if (filters?.year) params.year = filters.year
  if (filters?.entry_type) params.entry_type = filters.entry_type
  if (filters?.review_status) params.review_status = filters.review_status
  const { data } = await http.get('/api/consolidation/elimination-entries', { params })
  return data.data ?? data ?? []
}

export async function getEliminationEntry(id: string, projectId: string): Promise<EliminationEntry> {
  const { data } = await http.get(`/api/consolidation/elimination-entries/${id}`, { params: { project_id: projectId } })
  return data.data ?? data
}

export async function createEliminationEntry(
  payload: EliminationEntryCreatePayload
): Promise<EliminationEntry> {
  const { data } = await http.post('/api/consolidation/elimination-entries', payload)
  return data.data ?? data
}

export async function updateEliminationEntry(
  id: string,
  projectId: string,
  payload: EliminationEntryUpdatePayload
): Promise<EliminationEntry> {
  const { data } = await http.put(`/api/consolidation/elimination-entries/${id}`, payload, {
    params: { project_id: projectId }
  })
  return data.data ?? data
}

export async function deleteEliminationEntry(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/elimination-entries/${id}`, { params: { project_id: projectId } })
}

export async function approveEliminationEntry(id: string, projectId: string): Promise<EliminationEntry> {
  const { data } = await http.post(
    `/api/consolidation/elimination-entries/${id}/review`,
    { status: 'approved', reason: null },
    { params: { project_id: projectId } }
  )
  return data.data ?? data
}

export async function rejectEliminationEntry(
  id: string,
  projectId: string,
  reason: string
): Promise<EliminationEntry> {
  const { data } = await http.post(
    `/api/consolidation/elimination-entries/${id}/review`,
    { status: 'rejected', reason },
    { params: { project_id: projectId } }
  )
  return data.data ?? data
}

export async function batchApproveEliminationEntries(
  ids: string[],
  projectId: string
): Promise<{ approved: string[]; failed: Array<{ id: string; error: string }> }> {
  const { data } = await http.post(
    '/api/consolidation/elimination-entries/batch-review',
    { ids, status: 'approved', reason: null },
    { params: { project_id: projectId } }
  )
  return data.data ?? data
}

export async function batchRejectEliminationEntries(
  ids: string[],
  projectId: string,
  reason: string
): Promise<{ rejected: string[]; failed: Array<{ id: string; error: string }> }> {
  const { data } = await http.post(
    '/api/consolidation/elimination-entries/batch-review',
    { ids, status: 'rejected', reason },
    { params: { project_id: projectId } }
  )
  return data.data ?? data
}

export async function carryForwardElimination(
  entryId: string,
  projectId: string,
  targetPeriod: number
): Promise<CarryForwardResult> {
  const { data } = await http.post(
    `/api/consolidation/elimination-entries/${entryId}/carry-forward`,
    {},
    { params: { project_id: projectId, target_period: targetPeriod } }
  )
  return data.data ?? data
}

export async function getEliminationSummary(
  projectId: string,
  year: number
): Promise<EliminationSummary> {
  const { data } = await http.get('/api/consolidation/elimination-entries/summary', {
    params: { project_id: projectId, year }
  })
  return data.data ?? data
}

// ─── Consol Trial Balance Extended Types ──────────────────────────────────────

export interface ConsolTrialBalanceEntry {
  id: string
  project_id: string
  year: number
  account_code: string
  account_name: string
  account_category: 'asset' | 'liability' | 'equity' | 'pl' // 资产/负债/权益/损益
  // 各公司审定数（key=公司编码, value=审定金额）
  company_amounts: Record<string, { debit: number; credit: number }>
  individual_sum: number       // 汇总数（借正贷负）
  consol_adjustment: number    // 合并调整
  consol_elimination: number   // 合并抵消
  consol_amount: number        // 合并数（借正贷负）
  // 抵消分录明细（可展开）
  elimination_details?: Array<{
    entry_id: string
    entry_no: string
    entry_type: EliminationEntryType
    debit: number
    credit: number
  }>
}

export interface ConsolTrialBalanceFilter {
  year: number
  account_category?: string
  company_codes?: string[]
  show_zero_only?: boolean
}

export async function getConsolTrialBalanceFull(
  projectId: string,
  filter: ConsolTrialBalanceFilter
): Promise<ConsolTrialBalanceEntry[]> {
  const params: Record<string, unknown> = {
    project_id: projectId,
    year: filter.year,
  }
  if (filter.account_category) params.account_category = filter.account_category
  if (filter.company_codes?.length) params.company_codes = filter.company_codes.join(',')
  if (filter.show_zero_only) params.show_zero_only = true
  const { data } = await http.get('/api/consolidation/trial-balance', { params })
  return data.data ?? data ?? []
}

export async function exportConsolTrialExcel(
  projectId: string,
  year: number
): Promise<string> {
  const { data } = await http.post(
    '/api/consolidation/trial-balance/export',
    {},
    { params: { project_id: projectId, year } }
  )
  return data.data ?? data
}

// ─── Internal Trade Extended ────────────────────────────────────────────────────

export type TradeEliminationStatus = 'pending' | 'partial' | 'completed'

export interface InternalTradeDetail {
  id: string
  project_id: string
  year: number
  trade_no: string
  trade_date: string
  seller_company_code: string
  seller_company_name?: string
  buyer_company_code: string
  buyer_company_name?: string
  trade_type: 'goods' | 'services' | 'assets' | 'other'
  trade_amount: string
  currency: string
  cost_amount?: string
  unrealized_profit?: string
  elimination_status: TradeEliminationStatus
  description?: string
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface TransactionMatrix {
  company_codes: string[]
  company_names?: Record<string, string>
  matrix: Record<string, Record<string, string>>
}

export interface AutoEliminationResult {
  generated_count: number
  entry_ids: string[]
  message: string
}

// ─── Internal Trade API ────────────────────────────────────────────────────────

export async function getInternalTradeList(projectId: string, year?: number): Promise<InternalTradeDetail[]> {
  const { data } = await http.get('/api/consolidation/internal-trades', {
    params: { project_id: projectId, ...(year && { year }) }
  })
  return data.data ?? data ?? []
}

export async function getTransactionMatrix(projectId: string, year: number): Promise<TransactionMatrix> {
  const { data } = await http.get('/api/consolidation/transaction-matrix', {
    params: { project_id: projectId, year }
  })
  return data.data ?? data
}

export async function generateAutoElimination(
  projectId: string,
  tradeIds: string[]
): Promise<AutoEliminationResult> {
  const { data } = await http.post(
    '/api/consolidation/internal-trades/auto-elimination',
    { trade_ids: tradeIds },
    { params: { project_id: projectId } }
  )
  return data.data ?? data
}

// ─── Internal Ar/AP ────────────────────────────────────────────────────────────

export type ArApReconciliationStatus = 'matched' | 'unmatched' | 'tolerance'

export interface InternalArApRow {
  id: string
  project_id: string
  year: number
  arap_no?: string
  company_code: string
  company_name?: string
  counterparty_code: string
  counterparty_name?: string
  my_account_code?: string
  my_account_name?: string
  arap_type: 'ar' | 'ap'  // 应收 / 应付
  my_book_amount: string   // 我方账面数
  counterparty_book_amount: string  // 对方账面数
  difference_amount: string
  difference_reason?: string
  reconciliation_status: ArApReconciliationStatus
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface ArApReconciliationResult {
  reconciled_count: number
  matched_count: number
  unmatched_count: number
  tolerance_count: number
}

export async function getInternalArApList(projectId: string, year?: number): Promise<InternalArApRow[]> {
  const { data } = await http.get('/api/consolidation/internal-ar-ap', {
    params: { project_id: projectId, ...(year && { year }) }
  })
  return data.data ?? data ?? []
}

export async function createInternalArAp(
  projectId: string,
  payload: Omit<InternalArApRow, 'id' | 'project_id' | 'is_deleted' | 'created_at' | 'updated_at'>
): Promise<InternalArApRow> {
  const { data } = await http.post('/api/consolidation/internal-ar-ap', payload, {
    params: { project_id: projectId }
  })
  return data.data ?? data
}

export async function updateInternalArAp(
  id: string,
  projectId: string,
  payload: Partial<InternalArApRow>
): Promise<InternalArApRow> {
  const { data } = await http.put(`/api/consolidation/internal-ar-ap/${id}`, payload, {
    params: { project_id: projectId }
  })
  return data.data ?? data
}

export async function deleteInternalArAp(id: string, projectId: string): Promise<void> {
  await http.delete(`/api/consolidation/internal-ar-ap/${id}`, {
    params: { project_id: projectId }
  })
}

export async function reconcileAllInternalArAp(
  projectId: string,
  year: number
): Promise<ArApReconciliationResult> {
  const { data } = await http.post('/api/consolidation/internal-ar-ap/reconcile', {}, {
    params: { project_id: projectId, year }
  })
  return data.data ?? data
}

export async function generateArApElimination(
  projectId: string,
  arapIds: string[]
): Promise<AutoEliminationResult> {
  const { data } = await http.post(
    '/api/consolidation/internal-ar-ap/auto-elimination',
    { arap_ids: arapIds },
    { params: { project_id: projectId } }
  )
  return data.data ?? data
}


// ─── Consol Report ────────────────────────────────────────────────────────────

export type ReportType = 'balance_sheet' | 'income_statement' | 'cash_flow'

export interface ConsolReportRow {
  line_no: string
  account_code: string
  account_name: string
  before_amount: string
  adjustment: string
  after_amount: string
  consol_amount: string
  notes?: string
}

export interface ConsolReportData {
  report_type: ReportType
  period: string
  rows: ConsolReportRow[]
  total_debit?: string
  total_credit?: string
  goodwill?: string
  minority_equity?: string
  minority_equity_liabilities?: string
  minority_profit?: string
  parent_net_profit?: string
}

export interface YoYAnalysis {
  account_code: string
  account_name: string
  current_amount: string
  prior_amount: string
  change: string
  change_pct: string
}

export async function getConsolReport(
  projectId: string,
  reportType: ReportType,
  period: string
): Promise<ConsolReportData> {
  const { data } = await http.get('/api/consolidation/reports', {
    params: { project_id: projectId, report_type: reportType, period }
  })
  return data.data ?? data
}

export async function saveConsolReport(
  projectId: string,
  reportType: ReportType,
  period: string,
  reportData: ConsolReportData
): Promise<ConsolReportData> {
  const { data } = await http.put(
    `/api/consolidation/reports`,
    { report_type: reportType, period, ...reportData },
    { params: { project_id: projectId } }
  )
  return data.data ?? data
}

export async function downloadConsolReportExcel(
  projectId: string,
  reportType: ReportType,
  period: string
): Promise<string> {
  const { data } = await http.post(
    '/api/consolidation/reports/export/excel',
    {},
    { params: { project_id: projectId, report_type: reportType, period } }
  )
  return data.data ?? data
}

export async function downloadConsolReportPDF(
  projectId: string,
  reportType: ReportType,
  period: string
): Promise<string> {
  const { data } = await http.post(
    '/api/consolidation/reports/export/pdf',
    {},
    { params: { project_id: projectId, report_type: reportType, period } }
  )
  return data.data ?? data
}

export async function getYoYAnalysis(
  projectId: string,
  reportType: ReportType,
  period: string
): Promise<YoYAnalysis[]> {
  const { data } = await http.get('/api/consolidation/reports/yoy', {
    params: { project_id: projectId, report_type: reportType, period }
  })
  return data.data ?? data ?? []
}

// ─── Consol Notes ─────────────────────────────────────────────────────────────

export interface ConsolScopeNote {
  seq: number
  company_name: string
  shareholding: string
  voting_rights: string
  is_included: boolean
  inclusion_date: string
  exit_date?: string
  notes?: string
}

export interface SubsidiaryNote {
  company_name: string
  registration_place: string
  business_nature: string
  registered_capital: string
  paid_capital: string
  shareholding: string
  minority_equity_end: string
}

export interface GoodwillNote {
  acquiree: string
  opening_balance: string
  current_increase: string
  current_decrease: string
  current_impairment: string
  closing_balance: string
}

export interface MinorityInterestNote {
  subsidiary_name: string
  opening_balance: string
  share_of_profit: string
  share_of_loss: string
  dividends_paid: string
  other_changes: string
  closing_balance: string
}

export interface InternalTradeNote {
  trade_type: string
  trade_amount: string
  elimination_amount: string
}

export interface InternalArApNote {
  arap_type: string
  debit_balance: string
  credit_balance: string
  after_elimination: string
}

export interface ForexTranslationNote {
  currency: string
  statement_rate: string
  income_expense_avg_rate: string
  translation_diff: string
}

export interface ConsolNotesData {
  consol_scope: ConsolScopeNote[]
  subsidiaries: SubsidiaryNote[]
  goodwill: GoodwillNote[]
  minority_interest: MinorityInterestNote[]
  internal_trades: InternalTradeNote[]
  internal_arap: InternalArApNote[]
  forex_translation: ForexTranslationNote[]
  other_matters: string
}

export async function getConsolScopeNotes(projectId: string, period: string): Promise<ConsolScopeNote[]> {
  const { data } = await http.get('/api/consolidation/notes/scope', {
    params: { project_id: projectId, period }
  })
  return data.data ?? data ?? []
}

export async function getSubsidiaryNotes(projectId: string, period: string): Promise<SubsidiaryNote[]> {
  const { data } = await http.get('/api/consolidation/notes/subsidiaries', {
    params: { project_id: projectId, period }
  })
  return data.data ?? data ?? []
}

export async function getGoodwillNotes(projectId: string, period: string): Promise<GoodwillNote[]> {
  const { data } = await http.get('/api/consolidation/notes/goodwill', {
    params: { project_id: projectId, period }
  })
  return data.data ?? data ?? []
}

export async function getMinorityInterestNotes(projectId: string, period: string): Promise<MinorityInterestNote[]> {
  const { data } = await http.get('/api/consolidation/notes/minority-interest', {
    params: { project_id: projectId, period }
  })
  return data.data ?? data ?? []
}

export async function getInternalTradeNotes(projectId: string, period: string): Promise<{
  trades: InternalTradeNote[]
  arap: InternalArApNote[]
}> {
  const { data } = await http.get('/api/consolidation/notes/internal-trades', {
    params: { project_id: projectId, period }
  })
  return data.data ?? data ?? { trades: [], arap: [] }
}

export async function getForexTranslationNotes(projectId: string, period: string): Promise<ForexTranslationNote[]> {
  const { data } = await http.get('/api/consolidation/notes/forex', {
    params: { project_id: projectId, period }
  })
  return data.data ?? data ?? []
}

export async function saveConsolNotes(
  projectId: string,
  period: string,
  notesData: Partial<ConsolNotesData>
): Promise<void> {
  await http.put(
    '/api/consolidation/notes/other-matters',
    { period, ...notesData },
    { params: { project_id: projectId } }
  )
}

export async function downloadConsolNotesExcel(
  projectId: string,
  period: string
): Promise<string> {
  const { data } = await http.post(
    '/api/consolidation/notes/export/excel',
    {},
    { params: { project_id: projectId, period } }
  )
  return data.data ?? data
}

export async function downloadConsolNotesPDF(
  projectId: string,
  period: string
): Promise<string> {
  const { data } = await http.post(
    '/api/consolidation/notes/export/pdf',
    {},
    { params: { project_id: projectId, period } }
  )
  return data.data ?? data
}
