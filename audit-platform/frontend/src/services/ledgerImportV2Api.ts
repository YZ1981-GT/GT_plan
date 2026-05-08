/**
 * Ledger Import v2 API service.
 * Wraps all v2 endpoints for the new import engine.
 */
import { api } from '@/services/apiProxy'
import { ledger } from '@/services/apiPaths'

const BASE = (pid: string) => `/api/projects/${pid}/ledger-import`

export interface SubmitBody {
  upload_token: string
  year: number
  confirmed_mappings: unknown[]
  force_activate?: boolean
  adapter_id?: string
}

export interface DiagnosticsResult {
  detection_evidence: Record<string, unknown> | null
  adapter_used: string | null
  adapter_score: number | null
  engine_version: string | null
  duration_ms: number | null
  errors: Array<{ code: string; severity: string; message: string }>
  progress_history: Array<{ phase: string; timestamp: string; message?: string }>
}

export interface RawExtraFieldsResult {
  fields: Array<{
    field_name: string
    row_count: number
    sample_values: string[]
  }>
}

export const ledgerImportV2Api = {
  /** 预检：上传文件并返回识别结果 */
  detect: (pid: string, formData: FormData) =>
    api.post(ledger.import.base(pid) + '/detect', formData),

  /** 提交导入作业 */
  submit: (pid: string, body: SubmitBody) =>
    api.post(ledger.import.base(pid) + '/submit', body),

  /** SSE 进度流 URL（不走 api.get，直接拼 URL 给 EventSource） */
  streamUrl: (pid: string, jobId: string) =>
    `${BASE(pid)}/jobs/${jobId}/stream`,

  /** 取消作业 */
  cancel: (pid: string, jobId: string) =>
    api.post(`${BASE(pid)}/jobs/${jobId}/cancel`),

  /** 重试失败作业 */
  retry: (pid: string, jobId: string) =>
    api.post(`${BASE(pid)}/jobs/${jobId}/retry`),

  /** 获取诊断详情 */
  diagnostics: (pid: string, jobId: string) =>
    api.get<DiagnosticsResult>(`${BASE(pid)}/jobs/${jobId}/diagnostics`),

  /** 获取 raw_extra 字段分布 */
  rawExtraFields: (pid: string, params?: { year?: number; table?: string }) =>
    api.get<RawExtraFieldsResult>(`/api/projects/${pid}/ledger/raw-extra-fields`, { params }),

  /** 获取列映射历史（跨项目复用） */
  getMappingHistory: (pid: string) =>
    api.get(`/api/projects/${pid}/column-mappings`),

  /** 从其他项目复制映射 */
  copyMappingFromProject: (pid: string, sourceProjectId: string) =>
    api.post(`/api/projects/${pid}/column-mappings/reference-copy`, { source_project_id: sourceProjectId }),

  /** 获取可参考的项目列表 */
  getReferenceProjects: (pid: string) =>
    api.get(`/api/projects/${pid}/column-mappings/reference-projects`),
}

export default ledgerImportV2Api
