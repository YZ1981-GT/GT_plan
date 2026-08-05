import { api } from '@/services/apiProxy'
import { deliverables } from '@/services/apiPaths/report'
import { wordExports } from '@/services/apiPaths/report'

export interface DeliverableItem {
  task_id: string
  project_id: string
  doc_type: string
  status: string
  file_name: string | null
  version_no: number
  file_size: number | null
  exporter_name: string | null
  exported_at: string | null
  template_type: string | null
  selected_sections: string[] | null
  /**
   * 能力标志（spec deliverable-lineage-wiring-and-writeback-closure 需求 6.5）。
   * 单一真源在后端 `app/services/deliverable_capabilities.py`，经列表 DTO 下发。
   * 🔴 前端**不得**再写一份 doc_type 白名单 —— 双真源改一处另一处不红。
   * 兼容旧后端：字段缺失时按 false 处理（入口隐藏，比误显示更安全）。
   */
  supports_writeback?: boolean
  supports_section_refresh?: boolean
  /**
   * 报表差异告警（需求 10.3）：列表行即可见「数字与按试算表重算不一致」。
   * 判定由后端 `should_block_confirm` 唯一入口给出 —— 前端**不得**自己写
   * `if (drift_report)`（`{"diffs": []}` 是非空对象但表示已比对且一致）。
   */
  drift_blocked?: boolean
  drift_reason?: string | null
}

export interface DeliverableListResponse {
  items: DeliverableItem[]
  grouped: Record<string, DeliverableItem[]>
}

/** 报表差异检测的单条差异（后端 financial_report_drift_service.compare_cells 产出） */
export interface DeliverableDriftDiff {
  row_code: string
  row_name: string
  sheet: string
  period: 'current' | 'prior'
  coord: string
  file_value: string
  expected_value: string
  diff: string
  /** 该格在被编辑的上一版是否就已不一致；无基线可比时该字段不存在 */
  pre_existing?: boolean
}

export interface DeliverableDriftReport {
  diffs?: DeliverableDriftDiff[]
  checked?: number
  variant?: string
  stale?: boolean
  /** upstream_changed / pre_existing / manual_edit / unknown */
  attribution?: string
  baseline_version_no?: number
  pre_existing_count?: number
  introduced_count?: number
  /** 检测不可用（映射配置损坏）时才有 */
  unavailable?: string
}

export interface DeliverableVersion {
  id: string
  word_export_task_id: string
  version_no: number
  file_path: string | null
  html_path: string | null
  file_size: number | null
  created_by: string
  created_at: string | null
  selected_sections: string[] | null
  created_via: string | null
  /**
   * 溯源展示字段（spec deliverable-lineage-wiring-and-writeback-closure 需求 11.1/11.2/10.3）。
   * 全部由后端派生下发；`is_stale` 是**三态**（null = 未知，不得当 false 显示成"最新"）。
   * 兼容旧后端：字段缺失时按 undefined 处理。
   */
  edited_by?: string | null
  edited_at?: string | null
  edited_by_name?: string | null
  bound_tb_hash?: string | null
  is_stale?: boolean | null
  drift_report?: DeliverableDriftReport | null
  /** 由后端 should_block_confirm 唯一入口判定，前端不得自己写 `if drift_report` */
  drift_blocked?: boolean
  drift_reason?: string | null
}

export interface ReportBodyRenderResult {
  task_id: string
  version_no: number
  download_url: string
  html_preview: string
  platform_persist_failed: boolean
  report_body_json: Record<string, unknown> | null
  validation_warning: string | null
}

export async function fetchDeliverables(
  projectId: string,
  params?: { doc_type?: string; status?: string; keyword?: string },
): Promise<DeliverableListResponse> {
  const qs = new URLSearchParams()
  if (params?.doc_type) qs.set('doc_type', params.doc_type)
  if (params?.status) qs.set('status', params.status)
  if (params?.keyword) qs.set('keyword', params.keyword)
  const suffix = qs.toString() ? `?${qs}` : ''
  return api.get<DeliverableListResponse>(`${deliverables.list(projectId)}${suffix}`)
}

export async function fetchVersionChain(projectId: string, taskId: string): Promise<DeliverableVersion[]> {
  return api.get<DeliverableVersion[]>(deliverables.versions(projectId, taskId))
}

export async function renderReportBody(
  projectId: string,
  body: {
    year: number
    opinion_type: string
    company_type?: string
    is_pie?: boolean
    include_emphasis?: boolean
    selected_sections?: string[]
  },
): Promise<ReportBodyRenderResult> {
  return api.post<ReportBodyRenderResult>(deliverables.renderReportBody(projectId), body)
}

// ─── 报告正文两阶段生成（preview → OPT 弹窗 → confirm，§11/§13.1） ───────────

/** preview 请求体 */
export interface ReportBodyPreviewRequest {
  year: number
  opinion_type: string
  /** 企业子类型（type_a..type_d）；留空由后端从项目/fallback 解析 */
  company_subtype?: string | null
  /** 报告详简版，默认 simple */
  template_variant?: string
}

/** preview 返回的单个可选段落（OPT 块） */
export interface OptionalSection {
  section_id: string
  description: string
  /** 段落预览文本（前若干字） */
  preview: string
  /** 默认是否保留（勾选） */
  default_keep: boolean
  /** 所属分组中文标题（报告正文段落 / 补充信息段落） */
  group: string
}

/** preview 响应体 */
export interface ReportBodyPreviewResult {
  preview_session_id: string
  optional_sections: OptionalSection[]
  missing_fields: string[]
  template_version: string
  company_subtype_resolved: string
}

/** confirm 请求体 */
export interface ReportBodyConfirmRequest {
  year: number
  preview_session_id: string
  /** 用户勾选结果：section_id → 是否保留 */
  optional_sections: Record<string, boolean>
}

/** confirm 响应体 */
export interface ReportBodyConfirmResult {
  task_id: string
  version_no: number
  download_url: string
  report_body_json: Record<string, unknown>
  validation_warning: string | null
}

/**
 * 报告正文生成第一步：preview（不落库）。
 * 返回可选段落清单 + 待补充字段，供 OptionalSectionDialog 展示。
 */
export async function previewReportBody(
  projectId: string,
  body: ReportBodyPreviewRequest,
): Promise<ReportBodyPreviewResult> {
  return api.post<ReportBodyPreviewResult>(deliverables.previewReportBody(projectId), body)
}

/**
 * 报告正文生成第二步：confirm（携 preview_session_id + 勾选入库，版本递增）。
 */
export async function confirmReportBody(
  projectId: string,
  body: ReportBodyConfirmRequest,
): Promise<ReportBodyConfirmResult> {
  return api.post<ReportBodyConfirmResult>(deliverables.confirmReportBody(projectId), body)
}

export function deliverableDownloadUrl(projectId: string, taskId: string, versionNo: number): string {
  return deliverables.download(projectId, taskId, versionNo)
}

/** 编制参考版（含内部提示的 with_notes 副本，§13.2）下载 URL。 */
export function deliverableGuidanceDownloadUrl(
  projectId: string,
  taskId: string,
  versionNo: number,
): string {
  return deliverables.guidanceDownload(projectId, taskId, versionNo)
}

export async function renderDisclosureNotes(
  projectId: string,
  body: { year: number; template_type?: string; selected_sections?: string[] },
) {
  return api.post<DeliverableExportResponse>(deliverables.renderDisclosureNotes(projectId), body)
}

export async function renderFinancialReports(
  projectId: string,
  body: {
    year: number
    template_type?: string
    report_types?: string[]
    /** audited（审定，默认）| unadjusted（未审） */
    data_mode?: 'audited' | 'unadjusted'
  },
) {
  return api.post<DeliverableExportResponse>(deliverables.renderFinancialReports(projectId), body)
}

export interface DeliverableExportResponse {
  task_id: string
  version_no: number
  download_url: string
  platform_persist_failed: boolean
  file_name: string | null
}

export interface CompletenessResult {
  passed: boolean
  missing_doc_types: string[]
  missing_financial_reports: string[]
  has_confirmed: boolean
  trio_consistent: boolean
  trio_message: string | null
  /**
   * 三件套各自绑定的 tb_hash（需求 11.3 三列对照）。
   * 键为 doc_type，值为完整 hash 或 null（该类尚未生成 / 无绑定）。
   * 兼容旧后端：字段缺失时按空处理。
   */
  trio_tb_hashes?: Record<string, string | null>
  /** 与多数不同的 doc_type（需求 11.4：给「重新生成这一类」入口） */
  trio_lagging?: string[]
  trio_majority_tb_hash?: string | null
  /** 不一致但无法判定滞后方（各类绑定互不相同）⇒ 建议三类一并重新生成 */
  trio_ambiguous?: boolean
  warnings: string[]
}

export async function fetchCompleteness(
  projectId: string,
  year: number,
): Promise<CompletenessResult> {
  return api.get<CompletenessResult>(deliverables.completeness(projectId, year))
}

export async function submitApproval(projectId: string, taskId: string) {
  return api.post(deliverables.submitApproval(projectId, taskId), {})
}

export async function approveDeliverable(projectId: string, taskId: string, year: number) {
  return api.post(deliverables.approve(projectId, taskId, year), {})
}

export async function rejectDeliverable(projectId: string, taskId: string, reason: string) {
  return api.post(deliverables.reject(projectId, taskId), { reason })
}

export async function archiveDeliverables(
  projectId: string,
  body: { year: number; force?: boolean },
) {
  return api.post<{ archived_count: number }>(deliverables.archive(projectId), body)
}

export async function createPackage(projectId: string, body: { year: number; ignore_incomplete?: boolean }) {
  return api.post<{ job_id: string; warnings: string[] }>(deliverables.packageDownload(projectId), body)
}

export function packageFileUrl(projectId: string, jobId: string) {
  return deliverables.packageFile(projectId, jobId)
}

export async function fetchOnlyOfficeHealth(projectId: string) {
  return api.get<{ available: boolean; enabled: boolean; message?: string }>(
    deliverables.onlyofficeHealth(projectId),
  )
}

export async function fetchOnlyOfficeConfig(
  projectId: string,
  taskId: string,
  versionNo: number,
  year: number,
) {
  return api.get<{ config: Record<string, unknown>; token: string; mode: string; documentType: string }>(
    deliverables.onlyofficeConfig(projectId, taskId, versionNo, year),
  )
}

export async function deleteDeliverable(projectId: string, taskId: string) {
  return api.delete<{ message: string }>(`/api/projects/${projectId}/deliverables/${taskId}`)
}

// ─── 一键生成全套（job_type=full_deliverables，audit-report-template-integration §14） ──

/** ExportJob 明细项 */
export interface ExportJobItem {
  id: string
  job_id: string
  word_export_task_id: string | null
  status: string
  error_message: string | null
  finished_at: string | null
}

/** ExportJob 响应（含进度 + payload metadata：kam_warning / resolved_optional_sections） */
export interface ExportJobResult {
  id: string
  project_id: string
  job_type: string
  status: string
  payload: Record<string, unknown> | null
  progress_total: number
  progress_done: number
  failed_count: number
  initiated_by: string
  created_at: string | null
  updated_at: string | null
  items: ExportJobItem[]
}

/** 一键生成全套请求体 */
export interface FullDeliverablesRequest {
  year: number
  template_variant?: string
  steps?: string[]
  optional_sections?: Record<string, boolean> | null
}

/**
 * 创建「一键生成全套」后台任务（同步执行：审定报表 → 未审报表 → 附注 → 报告正文）。
 * 返回 ExportJob（含进度与明细），前端据 job_id 轮询 fetchExportJob。
 */
export async function createFullDeliverables(
  projectId: string,
  body: FullDeliverablesRequest,
): Promise<ExportJobResult> {
  return api.post<ExportJobResult>(wordExports.fullDeliverables(projectId), body)
}

/** 轮询全套生成任务进度。 */
export async function fetchExportJob(
  projectId: string,
  jobId: string,
): Promise<ExportJobResult> {
  return api.get<ExportJobResult>(wordExports.jobStatus(projectId, jobId))
}

// ─── 章节状态（溯源锚点是否已写入的唯一判据，需求 6.4）────────────────────

export interface DeliverableSectionStateItem {
  section_code: string
  source_snapshot_hash: string | null
  is_stale: boolean
  last_writeback_baseline_hash: string | null
  anchor_name: string | null
  rendered_block_hash?: string | null
  block_locate_mode?: string | null
  version_no: number | null
}

/**
 * 拉取出品物章节状态列表。
 *
 * `sections` 为空数组即「该出品物无锚点」——这是判定「旧版本出品物、
 * 溯源不可用」的**唯一判据**（不可由前端按 doc_type 猜测）。
 */
export async function fetchSectionStates(projectId: string, taskId: string) {
  return api.get<{ sections: DeliverableSectionStateItem[] }>(
    `/api/projects/${projectId}/deliverables/${taskId}/section-states`,
  )
}
