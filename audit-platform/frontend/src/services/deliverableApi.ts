import { api } from '@/services/apiProxy'
import { deliverables } from '@/services/apiPaths/report'

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
  body: { year: number; template_type?: string; report_types?: string[] },
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
