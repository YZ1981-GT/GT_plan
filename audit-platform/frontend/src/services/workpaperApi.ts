/**
 * 底稿模块 API 服务层
 * 封装模板管理、取数公式、WOPI、底稿管理、质量自检、复核批注全部 API
 */
import http, { downloadFile } from '@/utils/http'
import {
  templates as P_tpl, formula as P_fm, workpapers as P_wp,
  wpReviews as P_wr, wpMapping as P_wm, sampling as P_samp,
  wpAI as P_wpai, partner as P_partner, jobs as P_jobs,
} from '@/services/apiPaths'

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
  wp_id?: string | null
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
  review_status?: string
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
  /** 解析后的工作簿数据（含 user_overrides 等扩展信息），后端按需返回 */
  parsed_data?: Record<string, any> | null
  /** 业务年度（部分接口返回） */
  year?: number | null
}

export interface OnlineEditSession {
  enabled: boolean
  maturity: string
  preferred_mode: 'online' | 'offline'
  wopi_src: string | null
  access_token: string | null
  editor_url: string | null
  editor_base_url: string | null
  /** @deprecated 已迁移至 Univer，保留向后兼容 */
  onlyoffice_url: string | null
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
  const { data } = await http.get(P_tpl.list, { params })
  return data
}

export async function uploadTemplate(body: {
  template_code: string; template_name: string;
  audit_cycle?: string; applicable_standard?: string;
  description?: string; named_ranges?: any[]
}): Promise<TemplateItem> {
  const { data } = await http.post(P_tpl.create, body)
  return data
}

export async function createTemplateVersion(code: string, changeType: string = 'minor'): Promise<TemplateItem> {
  const { data } = await http.post(P_tpl.versions(code), { change_type: changeType })
  return data
}

export async function deleteTemplate(templateId: string) {
  const { data } = await http.delete(P_tpl.delete(templateId))
  return data
}

export async function listTemplateSets(): Promise<TemplateSetItem[]> {
  const { data } = await http.get(P_tpl.sets.list)
  return data
}

export async function getTemplateSet(setId: string): Promise<TemplateSetItem> {
  const { data } = await http.get(P_tpl.sets.detail(setId))
  return data
}

export async function createTemplateSet(body: {
  set_name: string; template_codes?: string[];
  applicable_audit_type?: string; description?: string
}): Promise<TemplateSetItem> {
  const { data } = await http.post(P_tpl.sets.list, body)
  return data
}

export async function updateTemplateSet(setId: string, body: Record<string, any>): Promise<TemplateSetItem> {
  const { data } = await http.put(P_tpl.sets.detail(setId), body)
  return data
}

// ─── Formula ───

export async function executeFormula(req: FormulaRequest): Promise<FormulaResult> {
  const { data } = await http.post(P_fm.execute, req)
  return data
}

export async function batchExecuteFormulas(reqs: FormulaRequest[]): Promise<FormulaResult[]> {
  const { data } = await http.post(P_fm.batchExecute, reqs)
  return data
}

// ─── Working Papers ───

/**
 * 统一「资源不存在或不可访问」文案（External_Not_Found）。
 *
 * Feature: procedure-delegation-visibility-isolation · Task 12 / Req 12.7。
 * 服务端对不存在、跨项目、越权、未映射页、历史版本等一律返回 HTTP 404 +
 * ``{"detail":"资源不存在或不可访问"}``；前端只显示此文案，绝不显示内部拒绝原因。
 */
export const EXTERNAL_NOT_FOUND_MESSAGE = '资源不存在或不可访问'

/**
 * 服务端可见性列表项（Task 8 组件 C13 分页 envelope 的单项）。
 *
 * 状态拆分（Req 12.4/12.5）：``index_status``（索引/目录层）与 ``file_status``（文件/编制层）
 * 分别返回，替代含义不明确的 legacy ``status``。``wp_id`` 可空——底稿尚未生成时为 ``null``，
 * ``wp_generated=false``，前端据此禁用依赖具体底稿资源的读取/写入动作（Req 12.8/12.9）。
 */
export interface VisibilityWpItem {
  wp_index_id: string
  project_id: string
  wp_id: string | null
  wp_code: string
  wp_name: string
  audit_cycle: string | null
  index_status: string | null
  file_status: string | null
  review_status: string
  assigned_to: string | null
  reviewer: string | null
  file_version: number | null
  file_path: string | null
  source_type: string | null
  prefill_stale: boolean
  /** 底稿是否已生成（wp_id 非空）。false → 前端禁用文件动作并显示"底稿尚未生成"。 */
  wp_generated: boolean
  created_at: string | null
  updated_at: string | null
}

/** 服务端分页 envelope（Req 11.6：仅 ``{items,total,stats,page,page_size}``）。 */
export interface WpVisibilityStats {
  by_index_status: Record<string, number>
  by_file_status: Record<string, number>
}

export interface WpListEnvelope {
  items: VisibilityWpItem[]
  total: number
  stats: WpVisibilityStats
  page: number
  page_size: number
}

/** nullable wp（底稿尚未生成）在 by_file_status 下的稳定 sentinel key（与后端一致）。 */
export const FILE_STATUS_NOT_GENERATED = 'not_generated'

const EMPTY_STATS: WpVisibilityStats = { by_index_status: {}, by_file_status: {} }

/** 归一化服务端分页 envelope（防御后端未来字段缺失，保证契约稳定）。 */
function normalizeEnvelope(data: any, page: number, pageSize: number): WpListEnvelope {
  const items = Array.isArray(data?.items) ? (data.items as VisibilityWpItem[]) : []
  const stats = data?.stats && typeof data.stats === 'object'
    ? {
        by_index_status: { ...(data.stats.by_index_status || {}) },
        by_file_status: { ...(data.stats.by_file_status || {}) },
      }
    : { ...EMPTY_STATS }
  return {
    items,
    total: Number.isFinite(data?.total) ? Number(data.total) : items.length,
    stats,
    page: Number.isFinite(data?.page) ? Number(data.page) : page,
    page_size: Number.isFinite(data?.page_size) ? Number(data.page_size) : pageSize,
  }
}

function normalizeWorkpaper(item: any): WorkpaperDetail {
  return {
    ...item,
    // 分页 envelope 项用 wp_id 标识具体底稿；legacy 数组项已带 id。
    id: item?.id ?? item?.wp_id,
    status: item?.status ?? item?.file_status ?? item?.index_status ?? 'not_started',
  }
}

/** 分页/排序/过滤参数（服务端强制可见性列表；Task 8 组件 C13）。 */
export interface WpListParams {
  audit_cycle?: string
  index_status?: string
  file_status?: string
  assigned_to?: string
  page?: number
  page_size?: number
  sort?: string
  sort_dir?: 'asc' | 'desc'
  /** 仅 UX，不参与服务端授权（Req 12.1–12.3 / Property 15）。 */
  visibility_mode?: string
}

/**
 * 底稿列表（服务端强制可见性 + 正式分页 + 状态拆分）。
 *
 * Feature: procedure-delegation-visibility-isolation · Task 12（消费 Task 8 组件 C13）。
 * 返回完整 envelope ``{items,total,stats,page,page_size}``（Req 11.6）；``visibility_mode``/
 * 客户端身份不改变授权（Req 12.1–12.3）。
 */
export async function listWorkpapersPaged(
  projectId: string,
  params: WpListParams = {},
): Promise<WpListEnvelope> {
  const page = params.page ?? 1
  const pageSize = params.page_size ?? 20
  const { data } = await http.get(P_wp.list(projectId), {
    params: { ...params, page, page_size: pageSize },
  })
  return normalizeEnvelope(data, page, pageSize)
}

/**
 * 我的主编底稿（MyLeadWorkpapers，Req 11.12/11.13）。
 *
 * 仅返回当前用户作为 Workpaper_Lead 的底稿，与「我的程序任务」（assignee/reviewer）为两个
 * 独立身份视图（Req 11.11：程序任务视图不合成主编项）。复用同一分页/去重/stats/排序契约。
 */
export async function listMyLeadWorkpapers(
  projectId: string,
  params: WpListParams = {},
): Promise<WpListEnvelope> {
  const page = params.page ?? 1
  const pageSize = params.page_size ?? 20
  const { data } = await http.get(P_wp.myLead(projectId), {
    params: { ...params, page, page_size: pageSize },
  })
  return normalizeEnvelope(data, page, pageSize)
}

/**
 * Legacy 底稿列表（返回扁平数组）。
 *
 * 服务端已把 ``/working-papers`` 升级为分页 envelope（Task 8），此函数对 envelope 与旧数组
 * 两种形态都兼容：envelope → 抽取 ``items``；数组 → 直接映射。新代码请改用
 * ``listWorkpapersPaged`` 消费完整分页/stats。
 */
export async function listWorkpapers(
  projectId: string,
  opts?: { audit_cycle?: string; status?: string; assigned_to?: string }
): Promise<WorkpaperDetail[]> {
  // legacy `status` 查询参数映射到 index_status（Req 12.6：legacy source → target）。
  const baseParams: Record<string, any> = { ...(opts || {}) }
  if (baseParams.status != null) {
    baseParams.index_status = baseParams.status
    delete baseParams.status
  }
  const PAGE_SIZE = 100 // 服务端上限
  const collected: any[] = []
  let page = 1
  // 服务端分页 envelope 上限 100/页：逐页拉取直至覆盖去重全集（保留 legacy「返回全部可见项」语义）。
  // 旧数组形态（未升级环境）第一次即返回全部，循环自然终止。
  for (;;) {
    const { data } = await http.get(P_wp.list(projectId), {
      params: { ...baseParams, page, page_size: PAGE_SIZE },
    })
    if (Array.isArray(data)) {
      collected.push(...data)
      break
    }
    const items = Array.isArray(data?.items) ? data.items : []
    collected.push(...items)
    const total = Number.isFinite(data?.total) ? Number(data.total) : collected.length
    if (items.length === 0 || collected.length >= total || page > 200) break
    page += 1
  }
  // legacy 消费者（Shell/试算表）期望「已生成的真实底稿」。分页 envelope 会含 nullable wp
  // （wp_generated=false，底稿尚未生成的可见 wp_index 行）——这些没有具体 WorkingPaper，
  // 过滤掉以保持 legacy 语义；wp_index 层信息由 getWpIndex 单独提供。
  const realized = collected.filter((it) => it?.wp_generated !== false)
  return realized.map(normalizeWorkpaper)
}

export async function getWorkpaper(projectId: string, wpId: string): Promise<WorkpaperDetail> {
  const { data } = await http.get(P_wp.detail(projectId, wpId))
  return normalizeWorkpaper(data)
}

export async function downloadWorkpaper(projectId: string, wpId: string) {
  return downloadFile(P_wp.download(projectId, wpId))
}

export async function downloadWorkpaperPack(projectId: string, wpIds?: string[], includePrefill: boolean = true) {
  return downloadFile(P_wp.downloadPack(projectId), {
    method: 'post',
    data: { wp_ids: wpIds, include_prefill: includePrefill },
    fileName: 'workpapers.zip',
  })
}

/** 下载单个科目的原始模板文件（从 wp_templates/ 目录） */
export async function downloadTemplate(projectId: string, wpCode: string) {
  return downloadFile(P_wp.templateDownload(projectId, wpCode))
}

/** 批量下载全部底稿模板（ZIP） */
export async function downloadAllTemplates(projectId: string) {
  return downloadFile(P_wp.templateDownloadAll(projectId), { fileName: '底稿模板全量.zip' })
}

export async function uploadWorkpaper(projectId: string, wpId: string, recordedVersion: number) {
  const { data } = await http.post(P_wp.upload(projectId, wpId), {
    recorded_version: recordedVersion,
  })
  return data
}

export async function uploadWorkpaperFile(
  projectId: string,
  wpId: string,
  file: File,
  uploadedVersion: number,
  forceOverwrite: boolean = false,
) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await http.post(
    `${P_wp.uploadFile(projectId, wpId)}?uploaded_version=${uploadedVersion}&force_overwrite=${forceOverwrite}`,
    formData,
  )
  return data
}

export async function getOnlineEditSession(projectId: string, wpId: string): Promise<OnlineEditSession> {
  const { data } = await http.get(P_wp.onlineSession(projectId, wpId))
  return data
}

export async function updateWorkpaperStatus(projectId: string, wpId: string, status: string) {
  const { data } = await http.put(P_wp.status(projectId, wpId), { status })
  return data
}

export async function updateReviewStatus(projectId: string, wpId: string, reviewStatus: string, reason?: string) {
  const body: Record<string, any> = { review_status: reviewStatus }
  if (reason) body.reason = reason
  const { data } = await http.put(P_wp.reviewStatus(projectId, wpId), body)
  return data
}

export async function assignWorkpaper(projectId: string, wpId: string, body: {
  assigned_to?: string | null; reviewer?: string | null
}) {
  const { data } = await http.put(P_wp.assign(projectId, wpId), body)
  return data
}

export async function prefillWorkpaper(projectId: string, wpId: string, year: number = 2025) {
  const { data } = await http.post(
    P_wp.prefill(projectId, wpId),
    null,
    { params: { year } },
  )
  return data
}

export async function parseWorkpaper(projectId: string, wpId: string, dryRun: boolean = false) {
  const { data } = await http.post(
    `${P_wp.parse(projectId, wpId)}${dryRun ? '?dry_run=true' : ''}`,
  )
  return data
}

export async function getWpIndex(projectId: string): Promise<WpIndexItem[]> {
  const { data } = await http.get(P_wp.wpIndex(projectId))
  return data
}

export async function getWpCrossRefs(projectId: string): Promise<CrossRefItem[]> {
  const { data } = await http.get(P_wp.wpCrossRefs(projectId))
  return data
}

// ─── QC ───

export async function runQCCheck(projectId: string, wpId: string): Promise<QCResult> {
  const { data } = await http.post(P_wp.qcCheck(projectId, wpId))
  return data
}

export async function getQCResults(projectId: string, wpId: string): Promise<QCResult> {
  const { data } = await http.get(P_wp.qcResults(projectId, wpId))
  return data
}

export async function getQCSummary(projectId: string): Promise<QCSummary> {
  const { data } = await http.get(P_wp.qcSummary(projectId))
  return data
}

// ─── Reviews ───

export async function listReviews(wpId: string, status?: string): Promise<ReviewComment[]> {
  const params: Record<string, string> = {}
  if (status) params.status = status
  const { data } = await http.get(P_wr.list(wpId), { params })
  return data
}

export async function addReview(wpId: string, body: {
  commenter_id: string; comment_text: string; cell_reference?: string
}): Promise<ReviewComment> {
  const { data } = await http.post(P_wr.list(wpId), body)
  return data
}

export async function replyReview(wpId: string, reviewId: string, body: {
  replier_id: string; reply_text: string
}): Promise<ReviewComment> {
  const { data } = await http.put(P_wr.reply(wpId, reviewId), body)
  return data
}

export async function resolveReview(wpId: string, reviewId: string, body: {
  resolved_by: string
}): Promise<ReviewComment> {
  const { data } = await http.put(P_wr.resolve(wpId, reviewId), body)
  return data
}

// ─── WOPI ───

/** @deprecated 已迁移至 Univer，保留向后兼容 */
export function getWopiEditorUrl(
  wopiSrc: string,
  onlyofficeUrl: string = 'http://localhost:8080',
): string {
  const normalizedBaseUrl = onlyofficeUrl.replace(/\/$/, '')
  return `${normalizedBaseUrl}/hosting/wopi/cell/edit?WOPISrc=${encodeURIComponent(wopiSrc)}`
}

/** @deprecated 已迁移至 Univer 纯前端，始终返回 true */
export async function checkOnlineEditingAvailability(): Promise<boolean> {
  return true
}


// ─── WP-Account Mapping ───

export interface WpAccountMapping {
  wp_code: string
  cycle: string
  wp_name: string
  account_codes: string[]
  account_name: string
  report_row: string | null
  note_section: string | null
}

export interface WpPrefillData {
  wp_code: string
  wp_name: string
  account_name: string
  report_row: string | null
  note_section: string | null
  accounts: Array<{
    code: string
    name: string
    unadjusted: string
    audited: string
    opening: string
    rje: string
    aje: string
  }>
  total_unadjusted: string
  total_audited: string
}

export async function getWpMappingByAccount(projectId: string, accountCode: string): Promise<WpAccountMapping[]> {
  const { data } = await http.get(P_wm.byAccount(projectId, accountCode))
  return data ?? []
}

export async function getWpPrefillData(projectId: string, wpCode: string, year: number): Promise<WpPrefillData | null> {
  const { data } = await http.get(P_wm.prefill(projectId, wpCode), { params: { year } })
  return data?.accounts ? data : null
}

export async function getAllWpMappings(projectId: string): Promise<WpAccountMapping[]> {
  const { data } = await http.get(P_wm.all(projectId))
  return data ?? []
}

export interface WpRecommendation extends WpAccountMapping {
  reason: string
  priority: 'required' | 'recommended' | 'optional'
}

export async function getWpRecommendations(projectId: string, year: number, reportScope: string = 'standalone'): Promise<WpRecommendation[]> {
  const { data } = await http.get(P_wm.recommend(projectId), { params: { year, report_scope: reportScope } })
  return data ?? []
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
  const { data } = await http.get(P_samp.configs.list(projectId))
  return data
}

export async function createSamplingConfig(projectId: string, body: Record<string, any>): Promise<SamplingConfigItem> {
  const { data } = await http.post(P_samp.configs.list(projectId), body)
  return data
}

export async function updateSamplingConfig(projectId: string, configId: string, body: Record<string, any>): Promise<SamplingConfigItem> {
  const { data } = await http.put(P_samp.configs.detail(projectId, configId), body)
  return data
}

export async function calculateSampleSize(projectId: string, body: Record<string, any>): Promise<{ method: string; params: Record<string, any>; calculated_size: number }> {
  const { data } = await http.post(P_samp.configs.calculate(projectId), body)
  return data
}

export async function listSamplingRecords(projectId: string, workingPaperId?: string): Promise<SamplingRecordItem[]> {
  const params: Record<string, string> = {}
  if (workingPaperId) params.working_paper_id = workingPaperId
  const { data } = await http.get(P_samp.records.list(projectId), { params })
  return data
}

export async function createSamplingRecord(projectId: string, body: Record<string, any>): Promise<SamplingRecordItem> {
  const { data } = await http.post(P_samp.records.list(projectId), body)
  return data
}

export async function updateSamplingRecord(projectId: string, recordId: string, body: Record<string, any>): Promise<SamplingRecordItem> {
  const { data } = await http.put(P_samp.records.detail(projectId, recordId), body)
  return data
}

export async function musSamplingEvaluate(projectId: string, recordId: string, misstatementDetails: Array<{ book_value: number; misstatement_amount: number }>): Promise<MUSEvaluationResult> {
  const { data } = await http.post(P_samp.records.musEvaluate(projectId, recordId), {
    misstatement_details: misstatementDetails,
  })
  return data
}

// ─── Phase 12: 审计说明智能生成 ───

export interface GenerateDraftResponse {
  generation_id: string
  prompt_version: string
  draft_text: string
  structured?: Record<string, string>
  data_sources: string[]
  confidence: string
  suggestions: string[]
}

export interface ConfirmDraftResponse {
  explanation_status: string
  last_parsed_sync_at?: string
}

export interface ReviewIssue {
  description: string
  severity: string
  suggested_action?: string
}

export interface WorkpaperReadinessCheck {
  check_name: string
  passed: boolean
  detail?: string
}

export interface WorkpaperReadinessResponse {
  all_passed: boolean
  checks: WorkpaperReadinessCheck[]
  total_workpapers: number
  check_duration_ms: number
}

export interface JobStatusResponse {
  id: string
  job_type: string
  status: string
  progress_total: number
  progress_done: number
  failed_count: number
  items: Array<{ id: string; wp_id: string; status: string; error_message?: string }>
  created_at: string
}

export async function generateExplanation(projectId: string, wpId: string): Promise<GenerateDraftResponse> {
  const { data } = await http.post(P_wpai.generateExplanation(projectId, wpId))
  return data
}

export async function confirmExplanation(projectId: string, wpId: string, generationId: string, finalText: string): Promise<ConfirmDraftResponse> {
  const { data } = await http.post(P_wpai.confirmExplanation(projectId, wpId), {
    generation_id: generationId, final_text: finalText,
  })
  return data
}

export async function refineExplanation(projectId: string, wpId: string, generationId: string, userEdits: string, feedback?: string) {
  const { data } = await http.post(P_wpai.refineExplanation(projectId, wpId), {
    generation_id: generationId, user_edits: userEdits, feedback,
  })
  return data
}

export async function reviewContent(projectId: string, wpId: string): Promise<{ issues: ReviewIssue[] }> {
  const { data } = await http.post(P_wpai.reviewContent(projectId, wpId))
  return data
}

export async function checkWorkpaperReadiness(projectId: string): Promise<WorkpaperReadinessResponse> {
  const { data } = await http.post(P_partner.workpaperReadiness(projectId))
  return data
}

export async function getJobStatus(projectId: string, jobId: string): Promise<JobStatusResponse> {
  const { data } = await http.get(P_jobs.status(projectId, jobId))
  return data
}

export async function retryJob(projectId: string, jobId: string) {
  const { data } = await http.post(P_jobs.retry(projectId, jobId))
  return data
}
