/**
  * 审计作业平台 API 服务层
  * 封装所有后端 API 调用
  */
 import type { AxiosRequestConfig } from 'axios'
 import http from '@/utils/http'
 import { api } from '@/services/apiProxy'
 import { resolveAuditYearFromProject } from '@/utils/resolveAuditYear'
 import {
   projects as P_proj, trialBalance as P_tb, adjustments as P_adj,
   materiality as P_mat, misstatements as P_mis, reports as P_rpt,
   cfsWorksheet as P_cfs, disclosureNotes as P_dn, auditReport as P_ar,
   exportTask as P_exp, workpaperSummary as P_ws,
 } from '@/services/apiPaths'
 import { fetchTrialBalanceRows } from '@/services/trialBalanceRows'
 import type { TrialBalanceRow } from '@/services/trialBalanceRows'

 export interface ProjectListItem {
   id: string
   name?: string | null
   client_name?: string | null
   audit_year?: number | string | null
   audit_period_end?: string | null
   audit_period_start?: string | null
 }

 export async function listProjects(): Promise<ProjectListItem[]> {
   const { data } = await http.get(P_proj.list)
   return Array.isArray(data) ? data : (data?.items ?? [])
 }

/** 项目详情：经 apiProxy 共享同址在途请求（R16：编辑器打开时项目 store / 页面各取一次，原先各发一条）。 */
 export async function getProject(projectId: string, opts: { dedupe?: boolean } = {}): Promise<ProjectListItem> {
  // dedupe:false：不进 http 层 GET 去重（项目 store 换项目时用：被同址 GET 取消会把年度误判成取失败）
  return api.get<ProjectListItem>(P_proj.detail(projectId), opts.dedupe === false ? ({ _dedupe: false } as any) : undefined)
}

export async function getProjectAuditYear(projectId: string): Promise<number | null> {
  const project = await getProject(projectId)
  return resolveAuditYearFromProject(project)
}

// ─── Trial Balance ───

export type { TrialBalanceRow }

export async function getTrialBalance(projectId: string, year: number, companyCode?: string): Promise<TrialBalanceRow[]> {
  const result = await fetchTrialBalanceRows(projectId, {
    year,
    companyCode,
  })
  return result.rows
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
  report_line?: string | null  // 对应报表行次名称（已确认映射的才有）
  balance?: string | null      // 传年度时附试算表审定数（参考余额）
}

export async function listAdjustments(
  projectId: string, year: number,
  opts?: { adjustment_type?: string; review_status?: string; origin?: string; page?: number; page_size?: number }
) {
  const { data } = await http.get(P_adj.list(projectId), {
    params: { year, ...opts },
  })
  return data
}

/** 取本年度全部分录组：后端每页最多 200，按 has_more 逐页取（原先只取第一页 200 组） */
export async function listAllAdjustments(projectId: string, year: number): Promise<any[]> {
  const items: any[] = []
  for (let page = 1; page <= 50; page += 1) {
    const res = await listAdjustments(projectId, year, { page, page_size: 200 })
    const batch: any[] = Array.isArray(res) ? res : (res?.items || [])
    items.push(...batch)
    const more = Array.isArray(res) ? false : (res?.has_more ?? batch.length === 200)
    if (!more || !batch.length) break
  }
  return items
}

/** 底稿调整分录组 → 集中登记（workpaper-adjustment-centralization） */
export async function syncAdjustmentFromWorkpaper(projectId: string, body: {
  year: number
  wp_id: string
  item_id: string
  source_wp_code: string
  description?: string
  adjustment_type: 'aje' | 'rje'
  company_code?: string
  line_items: Array<{
    standard_account_code?: string; account_name?: string; report_line_code?: string
    debit_amount: number; credit_amount: number
  }>
}) {
  // 调用方（useAdjustmentCentralSync）按错误码自管提示 ⇒ 静默，免得全局拦截器先弹一次
  const { data } = await http.post(P_adj.syncFromWorkpaper(projectId), body, { _silent: true } as any)
  return data
}

/** 按 source_ref 回流集中登记复核状态（底稿侧只读展示） */
export async function getAdjustmentBySourceRef(projectId: string, sourceRef: string) {
  const { data } = await http.get(P_adj.bySourceRef(projectId), { params: { source_ref: sourceRef } })
  return data as {
    entry_group_id?: string; adjustment_no?: string; adjustment_type?: string
    review_status?: string; rejection_reason?: string | null; source_wp_code?: string
    collaboration_status?: string | null
  }
}

/** 调整大厅写操作（新建 / 修改 / 删除 / 撤回复核）的调用方都自管失败提示 ⇒ 静默 */
const ADJ_SILENT = { _silent: true } as any

export interface AdjustmentLineInput {
  standard_account_code: string
  account_name?: string
  detail_account_code?: string | null
  report_line_code?: string | null
  debit_amount: number
  credit_amount: number
}

export async function createAdjustment(projectId: string, body: {
  adjustment_type: string; year: number; company_code?: string;
  /** 自定义编号（不填自动编号；同项目同年度不得重复） */
  adjustment_no?: string
  description?: string; line_items: AdjustmentLineInput[]
}) {
  const { data } = await http.post(P_adj.create(projectId), body, ADJ_SILENT)
  return data
}

// ── 调整分录协作接力（adjustment-collaboration-and-propagation） ──

export interface AdjCollabLineItem {
  standard_account_code?: string; account_name?: string; report_line_code?: string
  debit_amount: number; credit_amount: number
}

/** 转派/重派分录组给项目成员补充 */
export async function assignAdjustmentCollaboration(
  projectId: string, entryGroupId: string, body: { assignee_id: string; year: number; note?: string }
) {
  const { data } = await http.post(P_adj.collabAssign(projectId, entryGroupId), body)
  return data
}

/** 分录组当前协作 + 事件时间线 */
export async function getGroupCollaboration(projectId: string, entryGroupId: string) {
  const { data } = await http.get(P_adj.collabByGroup(projectId, entryGroupId))
  return data as {
    collaboration: null | {
      id: string; entry_group_id: string; status: string; round: number
      initiator_id: string; assignee_id: string; note?: string | null; rejection_reason?: string | null
    }
    timeline: Array<{ id: string; event_type: string; actor_id: string; payload: any; created_at: string | null }>
  }
}

/** 被指派人待办 */
export async function getCollaborationInbox(projectId: string) {
  const { data } = await http.get(P_adj.collabInbox(projectId))
  return data as Array<{
    id: string; entry_group_id: string; status: string; round: number
    initiator_id: string; note?: string | null; updated_at: string | null
  }>
}

export async function acknowledgeCollaboration(projectId: string, cid: string) {
  const { data } = await http.post(P_adj.collabAcknowledge(projectId, cid))
  return data
}

export async function contributeCollaboration(
  projectId: string, cid: string, body: { line_items: AdjCollabLineItem[]; note?: string }
) {
  const { data } = await http.post(P_adj.collabContribute(projectId, cid), body)
  return data
}

export async function confirmCollaboration(projectId: string, cid: string) {
  const { data } = await http.post(P_adj.collabConfirm(projectId, cid))
  return data
}

export async function rejectCollaboration(projectId: string, cid: string, reason: string) {
  const { data } = await http.post(P_adj.collabReject(projectId, cid), { reason })
  return data
}

export async function updateAdjustment(projectId: string, groupId: string, body: {
  description?: string; line_items: AdjustmentLineInput[]
}) {
  const { data } = await http.put(P_adj.detail(projectId, groupId), body, ADJ_SILENT)
  return data
}

export async function deleteAdjustment(projectId: string, groupId: string) {
  const { data } = await http.delete(P_adj.detail(projectId, groupId), ADJ_SILENT)
  return data
}

/** 撤回复核（approved→draft）（chain-closure-phase3-push-rollout 需求 3.1）；返回含 notified（通知了谁） */
export async function revokeAdjustmentReview(projectId: string, groupId: string, body: {
  reason?: string
}) {
  const { data } = await http.post(P_adj.revokeReview(projectId, groupId), body, ADJ_SILENT)
  return data
}

export async function getAdjustmentSummary(projectId: string, year: number): Promise<AdjustmentSummary> {
  const { data } = await http.get(P_adj.summary(projectId), { params: { year } })
  return data
}

export async function getAccountDropdown(
  projectId: string, reportLineCode?: string, year?: number | null,
): Promise<AccountOption[]> {
  const params: Record<string, string | number> = {}
  if (reportLineCode) params.report_line_code = reportLineCode
  if (year != null) params.year = year
  const { data } = await http.get(P_adj.accountDropdown(projectId), { params })
  return data
}

// ── 调整分录复核流转 / 导入（spec adjustment-hall-entry-review-closure）──
// 调用方自管提示 ⇒ 一律 _silent（否则全局拦截器先弹一次，同一原因提示两遍）

export interface AdjustmentReviewer {
  user_id: string
  name: string
  project_role: string | null
  system_role: string
}

export interface AdjustmentFlowItem {
  entry_group_id: string
  adjustment_no?: string | null
  status?: string
  previous_status?: string
  reason?: string
  [key: string]: unknown
}

export interface AdjustmentFlowResult {
  succeeded: AdjustmentFlowItem[]
  failed: Array<{ entry_group_id: string; adjustment_no: string | null; reason: string }>
  notified: Array<{ user_id: string; name: string; kind: string }>
  warning?: string | null
}

export async function listAdjustmentReviewers(projectId: string): Promise<AdjustmentReviewer[]> {
  const { data } = await http.get(P_adj.reviewers(projectId), { _silent: true } as any)
  return data
}

export async function submitAdjustmentsForReview(projectId: string, body: {
  entry_group_ids: string[]; reviewer_ids?: string[]; note?: string
}): Promise<AdjustmentFlowResult> {
  const { data } = await http.post(P_adj.submitReview(projectId), body, { _silent: true } as any)
  return data
}

export async function withdrawAdjustmentSubmission(projectId: string, groupId: string) {
  const { data } = await http.post(P_adj.withdrawSubmission(projectId, groupId), null, { _silent: true } as any)
  return data
}

export async function reviewAdjustmentsBatch(projectId: string, body: {
  entry_group_ids: string[]; status: 'approved' | 'rejected'; reason?: string; reasons?: Record<string, string>
}): Promise<AdjustmentFlowResult> {
  const { data } = await http.post(P_adj.reviewBatch(projectId), body, { _silent: true } as any)
  return data
}

export async function batchDeleteAdjustments(projectId: string, ids: string[]): Promise<{
  succeeded: string[]; failed: Array<{ id: string; error: string }>
}> {
  const { data } = await http.post(P_adj.batchDelete(projectId), { ids }, { _silent: true } as any)
  return data
}

export interface AdjustmentImportPreviewGroup {
  key: string
  adjustment_no: string
  adjustment_type: 'AJE' | 'RJE'
  description: string
  rows: number[]
  lines: Array<{ label: string; account_code: string; account_name: string; debit: string; credit: string }>
  total_debit: string
  total_credit: string
  action: 'create' | 'replace' | 'skip'
  skip_reason: string | null
  errors: string[]
  ok: boolean
}

export interface AdjustmentImportPreview {
  mode: 'append' | 'overwrite'
  groups: AdjustmentImportPreviewGroup[]
  warnings: string[]
  structure_errors: string[]
  summary: { total: number; ok: number; error: number; skip: number; replace: number }
  example_skipped: number
}

export interface AdjustmentImportResult {
  imported: number
  skipped: number
  failed: number
  failed_rows: Array<{ row: number; adj_no: string; rows_in_group: number[]; error: string }>
  skipped_rows?: Array<{ row: number; adj_no: string; rows_in_group: number[]; reason: string }>
  created: Array<{ key: string; entry_group_id: string; adjustment_no: string | null }>
  warnings: string[]
  message: string
}

function _importForm(file: File): FormData {
  const form = new FormData()
  form.append('file', file)
  return form
}

export async function previewAdjustmentImport(
  projectId: string, year: number, mode: 'append' | 'overwrite', file: File,
): Promise<AdjustmentImportPreview> {
  const { data } = await http.post(P_adj.importPreview(projectId), _importForm(file), {
    params: { year, mode }, headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000, _silent: true,
  } as any)
  return data
}

export async function importAdjustmentsFile(
  projectId: string, year: number, mode: 'append' | 'overwrite', file: File,
): Promise<AdjustmentImportResult> {
  const { data } = await http.post(P_adj.importFile(projectId), _importForm(file), {
    params: { year, mode }, headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000, _silent: true,
  } as any)
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

export async function getMaterialityBenchmark(projectId: string, year: number, benchmarkType: string, calcBasis: string = 'unadjusted') {
  const { data } = await http.get(P_mat.benchmark(projectId), {
    params: { year, benchmark_type: benchmarkType, calc_basis: calcBasis },
  })
  return data
}

// ─── Events SSE ───
// 项目事件流统一走单例总线 `services/sse/projectEventStream`（每项目一条共享连接）。
// 旧 createEventSource 兼容包装（无调用方）已移除以避免绕过总线直连 /events/stream
// （frontend-sse-connection-consolidation R6.3）。


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
  source_wp_code?: string | null
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
  /** null = 没有任何可执行的审核项（见 noResult），不是「全部通过」 */
  consistent: boolean | null
  /** 0 条可执行：报表未生成且未配置审核公式 */
  noResult: boolean
  checks: Array<{
    name: string; passed: boolean; expected: string; actual: string; diff: string
    category: string; category_label: string; formula: string | null; source: string
  }>
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

/**
 * 报表「审核」结果映射。🔴 汇总计数与 category 必须透传：审核弹窗按 category 分页签、
 * 按 total / *_passed 出统计 —— 早先只映射 consistent / checks 五个字段，弹窗统计恒 0、
 * 两个分类页签恒空（spec formula-governance-coverage-closure R1.6）。
 */
export function mapReportConsistencyCheck(raw: any): ReportConsistencyCheck {
  const checks = (raw?.checks || []).map((item: any) => ({
    name: item.name ?? item.check_name ?? '',
    passed: !!item.passed,
    expected: item.expected ?? item.expected_value ?? '',
    actual: item.actual ?? item.actual_value ?? '',
    diff: item.diff ?? item.difference ?? '',
    category: item.category ?? 'logic_check',
    category_label: item.category_label ?? '',
    formula: item.formula ?? null,
    source: item.source ?? '',
  }))
  const noResult = raw?.no_result ?? checks.length === 0
  return {
    consistent: noResult ? null : (raw?.consistent ?? raw?.all_passed ?? false),
    noResult,
    checks,
    total: raw?.total ?? checks.length,
    logic_check_count: raw?.logic_check_count,
    logic_check_passed: raw?.logic_check_passed,
    reasonability_count: raw?.reasonability_count,
    reasonability_passed: raw?.reasonability_passed,
  }
}

export async function getReportConsistencyCheck(projectId: string, year: number): Promise<ReportConsistencyCheck> {
  const { data: raw } = await http.get(P_rpt.consistencyCheck(projectId, year))
  return mapReportConsistencyCheck(raw)
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
  /** 是否过期（stale 标记，后端 query_builder 路径下发；树端点可能不含 → 可选） */
  is_stale?: boolean
  /** 是否空章节（前端离线导出按此判定 has_data；后端树端点可能不含 → 可选） */
  is_empty?: boolean
  /** 最新校验 findings 计数（树端点 additive 附加；P0-4 校验落库后后端注入） */
  findings?: { error: number; warning: number }
}

export interface DisclosureNoteDetail {
  id: string
  note_section: string
  section_title: string
  account_name: string | null
  content_type: string
  table_data: any
  text_content: string | null
  guidance_text?: string | null
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

/**
 * 本项目附注目录。附注未生成时后端 404「附注数据不存在，请先生成附注」是正常空态 ——
 * 调用方可传 `{ _silent: true }` 自己处理（原先只收两个参数，第三参被丢弃 ⇒ 公式管理中心 / AI 采纳目标
 * 每次都弹全局错误提示，spec formula-governance-coverage-closure R5 走查）。
 */
export async function getDisclosureNoteTree(
  projectId: string, year: number, config?: AxiosRequestConfig,
): Promise<DisclosureNoteTreeItem[]> {
  const { data } = await http.get(P_dn.tree(projectId, year), config)
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

export async function validateDisclosureNotes(
  projectId: string,
  year: number,
  templateType?: 'soe' | 'listed',
) {
  // 后端仅接受 soe/listed（决定预设公式集）；custom 等其他值不传，用后端默认
  const url = P_dn.validate(projectId, year)
  const finalUrl = templateType ? `${url}?template_type=${templateType}` : url
  const { data } = await http.post(finalUrl)
  return data
}

export async function getValidationResults(projectId: string, year: number): Promise<NoteValidationFinding[]> {
  const { data } = await http.get(P_dn.validationResults(projectId, year))
  // 后端返回 { findings: [...] } 结构化对象；兼容直接返回数组的旧形态
  if (Array.isArray(data)) return data
  return (data?.findings ?? []) as NoteValidationFinding[]
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
