import { api } from '@/services/apiProxy'
import { ledger as P } from '@/services/apiPaths'

export interface LedgerDataset {
  id: string
  status: string
  source_type?: string
  source_summary?: Record<string, unknown> | null
  record_summary?: Record<string, unknown> | null
  validation_summary?: Record<string, unknown> | null
  created_at?: string | null
  activated_at?: string | null
  previous_dataset_id?: string | null
}

export interface ImportJob {
  id: string
  year: number
  status: string
  current_phase?: string | null
  progress_pct: number
  progress_message?: string | null
  error_message?: string | null
  result_summary?: Record<string, unknown> | null
  retry_count: number
  max_retries?: number
  created_at?: string | null
  started_at?: string | null
  completed_at?: string | null
}

export interface ImportJobStatus extends ImportJob {
  progress?: number
  message?: string | null
  result?: Record<string, unknown> | null
}

export interface ActivationRecord {
  id: string
  dataset_id: string
  action: string
  previous_dataset_id?: string | null
  performed_at?: string | null
  reason?: string | null
}

export interface ImportArtifact {
  id: string
  upload_token: string
  status: string
  storage_uri?: string | null
  checksum?: string | null
  total_size_bytes: number
  file_manifest?: Array<Record<string, unknown>> | null
  file_count: number
  expires_at?: string | null
  created_at?: string | null
}

function base(projectId: string) {
  return P.import.base(projectId)
}

export async function listLedgerDatasets(projectId: string, year: number): Promise<LedgerDataset[]> {
  const data = await api.get(`${base(projectId)}/datasets`, { params: { year } })
  return data ?? []
}

export async function getActiveLedgerDataset(projectId: string, year: number): Promise<{ active_dataset_id: string | null; source_summary?: Record<string, any> }> {
  const data = await api.get(`${base(projectId)}/datasets/active`, { params: { year } })
  return data ?? { active_dataset_id: null }
}

export async function rollbackLedgerDataset(projectId: string, datasetId: string, year: number, reason?: string) {
  return await api.post(`${base(projectId)}/datasets/${datasetId}/rollback`, null, {
    params: { year, reason },
  })
}

export async function listImportJobs(projectId: string, year?: number): Promise<ImportJob[]> {
  const data = await api.get(`${base(projectId)}/jobs`, { params: year ? { year } : {} })
  return data ?? []
}

export async function retryImportJob(projectId: string, jobId: string) {
  return await api.post(`${base(projectId)}/jobs/${jobId}/retry`)
}

export async function cancelImportJob(projectId: string, jobId: string) {
  return await api.post(`${base(projectId)}/jobs/${jobId}/cancel`)
}

export async function getImportJob(projectId: string, jobId: string): Promise<ImportJobStatus> {
  return await api.get(`${base(projectId)}/jobs/${jobId}`)
}

export async function smartPreviewLedgerImport(projectId: string, url: string, formData: FormData) {
  void projectId
  return await api.post(url, formData, { timeout: 600000 })
}

export async function submitSmartLedgerImport(projectId: string, url: string, formData: FormData) {
  void projectId
  return await api.post(url, formData, { timeout: 60000 })
}

export async function listActivationRecords(projectId: string, year: number): Promise<ActivationRecord[]> {
  const data = await api.get(`${base(projectId)}/activation-records`, { params: { year } })
  return data ?? []
}

export async function listImportArtifacts(projectId: string): Promise<ImportArtifact[]> {
  const data = await api.get(`${base(projectId)}/artifacts`)
  return data ?? []
}
