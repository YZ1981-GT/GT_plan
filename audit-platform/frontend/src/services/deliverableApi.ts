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
}

export interface DeliverableListResponse {
  items: DeliverableItem[]
  grouped: Record<string, DeliverableItem[]>
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
