import http, { downloadFile } from '@/utils/http'

export type BatchProjectMode = 'project' | 'consolidation'

export const BATCH_PROJECT_CREATE_ROLES = new Set(['admin', 'partner', 'manager'])
export const BATCH_PLAN_STATUS = {
  validated: 'validated', applying: 'applying', applied: 'applied', failed: 'failed',
} as const

export function canBatchCreateProjects(role: string | null | undefined): boolean {
  return BATCH_PROJECT_CREATE_ROLES.has((role || '').trim().toLowerCase())
}

export interface BatchImportFailure {
  row_number: number
  errors: string[]
}

export interface BatchSummary {
  create: number
  update: number
  unchanged: number
  skip: number
  auto_root: number
  error: number
}

export interface BatchWarning {
  row_number: number
  messages: string[]
}

export interface PreviewTreeNode {
  id: string
  nodeKey?: string
  label: string
  companyCode: string | null
  companyName: string | null
  relation?: 'subsidiary' | 'branch' | string | null
  year?: number | null
  consolidatedProjectId?: string | null
  standaloneProjectId?: string | null
  via?: Array<{ companyCode: string; companyName: string }>
  flags?: string[]
  isDetached?: boolean
  isCycleBreak?: boolean
  hasNoCompanyCode?: boolean
  plannedAction?: 'create' | 'update' | 'unchanged' | 'auto_root'
  children?: PreviewTreeNode[]
}

export interface PreviewGroupTree {
  key?: string
  year?: number | null
  ultimateCode: string | null
  ultimateName: string | null
  rootProjectId: string | null
  children: PreviewTreeNode[]
}

export interface BatchValidateResponse {
  valid: boolean
  total_rows: number
  tree_preview: PreviewGroupTree[]
  errors: BatchImportFailure[]
  warnings: BatchWarning[]
  summary: BatchSummary
  validation_id: string | null
  file_sha256: string | null
  template_version: string | null
  expires_at: string | null
}

export interface BatchImportResult {
  success_count: number
  fail_count: number
  failures: BatchImportFailure[]
  created_count: number
  updated_count: number
  unchanged_count: number
  skipped_count: number
  auto_root_count: number
  project_ids: string[]
  root_project_ids: string[]
  idempotent: boolean
}

export interface BatchPlanStatus {
  validation_id: string
  mode: BatchProjectMode
  status: string
  valid: boolean
  total_rows: number
  errors: BatchImportFailure[]
  summary: BatchSummary & { global_errors?: string[] }
  tree_preview: PreviewGroupTree[]
  warnings: BatchWarning[]
  template_version: string | null
  receipt: BatchImportResult | null
  public_error: string | null
  expires_at: string
}

export function newBatchIdempotencyKey(): string {
  return typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `batch-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export async function validateBatchProjectFile(
  file: File,
  mode: BatchProjectMode,
  idempotencyKey: string,
): Promise<BatchValidateResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('idempotency_key', idempotencyKey)
  const response = await http.post(`/api/projects/batch-validate?mode=${mode}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    _silent: true,
  } as any)
  return response.data as BatchValidateResponse
}

export async function applyBatchProjectPlan(
  validationId: string,
  idempotencyKey: string,
): Promise<BatchImportResult> {
  const response = await http.post('/api/projects/batch-apply', {
    validation_id: validationId,
    idempotency_key: idempotencyKey,
  }, { _silent: true } as any)
  return response.data as BatchImportResult
}

export async function getBatchProjectPlan(validationId: string): Promise<BatchPlanStatus> {
  const response = await http.get(`/api/projects/batch-imports/${validationId}`, {
    _silent: true,
  } as any)
  return response.data as BatchPlanStatus
}

export async function downloadBatchTemplate(mode: BatchProjectMode): Promise<void> {
  await downloadFile(`/api/projects/batch-template?mode=${mode}`, {
    fileName: mode === 'consolidation' ? '合并批量建项模板.xlsx' : '建项模板.xlsx',
    silent: true,
  })
}

export async function downloadGroupImportTemplate(projectId: string): Promise<void> {
  await downloadFile(`/api/projects/${projectId}/group-import-template`, {
    fileName: '当前集团树.xlsx',
    silent: true,
  })
}

export async function downloadSelectedProjectTemplate(projectIds: string[]): Promise<void> {
  await downloadFile('/api/projects/batch-export', {
    method: 'post',
    data: { project_ids: projectIds },
    fileName: '项目数据导出.xlsx',
    silent: true,
  })
}

export async function downloadBatchErrors(validationId: string): Promise<void> {
  await downloadFile(`/api/projects/batch-imports/${validationId}/errors.xlsx`, {
    fileName: '批量建项错误明细.xlsx',
    silent: true,
  })
}

export function batchErrorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail ?? error?.response?.data?.message
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const text = detail.map((item) => item?.msg || item?.message).filter(Boolean).join('；')
    if (text) return text
  }
  if (detail && typeof detail === 'object') {
    const text = detail.message || detail.msg || detail.error
    if (typeof text === 'string' && text.trim()) return text
  }
  if (typeof error?.message === 'string' && error.message.trim()) return error.message
  return fallback
}
